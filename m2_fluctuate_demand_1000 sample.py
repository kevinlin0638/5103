import pandas as pd
import numpy as np
from gurobipy import Model, GRB
import matplotlib.pyplot as plt
import numpy as np
import json
from tqdm import tqdm


model = Model("Optimization")

# 1. Parameter

# 1.1 Time
period = 1  # number of hours
T = int(48 / period)  # 1 day
# ($/MWh)

# 1.2 Price

prices = pd.read_csv('./data/USEP_08Nov2023_to_14Nov2023.csv')

ctb = prices['USEP ($/MWh)']

selling_price_discount = 0.9

# 1.3 Demand in kwh
consumption_mean = 111.87*0.5
consumption_std_dev = 9.86*0.5


# 1.4 Battery
number_of_battery = 1
battery_cost = 11.35 # per day
DC_AC_efficiency = 0.94

total_battery_cost = battery_cost*number_of_battery  # per day

single_battery_capacity_kwh = 150 # Battery capacity is fixed
Beta_max = single_battery_capacity_kwh * number_of_battery  # maximum battery capacity (define this)

Sample_Size = 1000

result_all = []
#cost_wo_battery= np.zeros(Sample_Size)
#cost_with_battery= np.zeros(Sample_Size)
#cost_difference= np.zeros(Sample_Size)

# 2. model run
for k in tqdm(range(Sample_Size), desc="Running Simulations", unit="simulation"):
    result_sample = {'sample': k, 'cost_w/o_battery': 0, 'time_steps': {}}
    consumption = np.random.normal(consumption_mean, consumption_std_dev, T)
    Ed = consumption.tolist()  # fixed load demand (define this)
    cost_wo_battery = sum(x * y/1000 for x, y in zip(Ed, ctb))
# ----------------------------------------------------------------
    E = model.addVars(3, 3, T, name="E")  # Energy variables Eijt
    y2tch = model.addVars(T, vtype=GRB.BINARY, name="y2tch")  # Binary variables for ESS charge state
    y2td = model.addVars(T, vtype=GRB.BINARY, name="y2td")  # Binary variables for ESS discharge state
    battery_power = model.addVars(T, name="battery_power")  # Current power of ESS

# ----------------------------------------------------------------

    model.setObjective(sum((ctb[t]/1000) * (E[0, 2, t] + E[0, 1, t])
                           - selling_price_discount * (ctb[t]/1000) * E[1, 0, t] for t in range(T))
                       + total_battery_cost
                       , GRB.MINIMIZE)

# ----------------------------------------------------------------
    # Fulfill load demand
    model.addConstrs((E[0, 2, t] + E[1, 2, t] == Ed[t] for t in range(T)), "LoadDemand")

    # ESS does not charge and discharge simultaneously
    model.addConstrs((y2tch[t] + y2td[t] <= 1 for t in range(T)), "ChargeDischarge")

    # ESS discharge does not exceed its current power
    model.addConstrs((E[1, 2, t] + E[1, 0, t] <= DC_AC_efficiency* battery_power[t] * y2td[t] for t in range(T)), "DischargeLimit")

    # ESS charge does not exceed what’s left
    model.addConstrs((DC_AC_efficiency* E[0, 1, t] <= (Beta_max - battery_power[t]) * y2tch[t] for t in range(T)), "ChargeLimit")
    model.addConstrs((DC_AC_efficiency* E[0, 1, t] <= Beta_max for t in range(T)), "ChargeLimit_2")

    # ESS power does not exceed its max capacity and is non-negative
    for t in range(T):
        model.addConstr(battery_power[t] >= 0, f"PowerLowerBound_{t}")
        model.addConstr(battery_power[t] <= Beta_max, f"PowerUpperBound_{t}")

    # ESS min charge/discharge 1MWh
    model.addConstrs((E[0, 1, t] >= y2tch[t] for t in range(T)), "ChargeConstraint")
    model.addConstrs((E[1, 2, t] >= y2td[t] for t in range(T)), "DischargeConstraint")

    # ESS current power is based on previous round power
    for t in range(1, T):
        model.addConstr(battery_power[t] == battery_power[t-1] - (E[1, 2, t-1] + E[1, 0, t-1]) * y2td[t-1] +
                        E[0, 1, t-1] * y2tch[t-1], "PowerUpdate")

    # Battery fully discharged at t=1
    model.addConstr(battery_power[0] == 0, "InitialDischarge")

    # ----------------------------------------------------------------
    model.setParam( 'OutputFlag', False )
    model.optimize()

    #cost_with_battery[i]=model.objVal
    #cost_difference[i]=cost_wo_battery[i]-cost_with_battery[i]

    if model.Status == GRB.OPTIMAL:
        result_sample['cost_w/o_battery'] = cost_wo_battery
        result_sample['cost_w_battery'] = model.objVal
        result_sample['cost_diff'] = cost_wo_battery - model.objVal

        for t in range (T):
            result_sample['time_steps'][t] = {
                'price': ctb[t]/1000,
                'battery_power': battery_power[t].X,
                'y2tch': y2tch[t].X,
                'y2td': y2td[t].X,
                'E': {}
            }
            for j in range(3):
                for k in range(3):
                    result_sample['time_steps'][t]['E'][f'{j}_{k}'] = E[j, k, t].X

    result_all.append(result_sample)

result_df = pd.DataFrame(result_all)

# Save to JSON
with open('./data/results_m2.json', 'w') as f:
    json.dump(result_all, f)


# ----------------------------------------------------------------

# 3.1 Result Analysis

# Initialize sums
total_cost_wo_battery = 0
total_cost_with_battery = 0
total_cost_difference = 0
successful_samples = 0

# Loop through all results and sum the required values
for result in result_all:
    if 'cost_w_battery' in result:  # This checks if the optimization was successful
        total_cost_wo_battery += result['cost_w/o_battery']
        total_cost_with_battery += result['cost_w_battery']
        total_cost_difference += result['cost_diff']
        successful_samples += 1

# Calculate averages
average_cost_wo_battery = total_cost_wo_battery / successful_samples if successful_samples > 0 else 0
average_cost_with_battery = total_cost_with_battery / successful_samples if successful_samples > 0 else 0
average_cost_difference = total_cost_difference / successful_samples if successful_samples > 0 else 0

# Print or store the averages as needed
print(f"Average cost without battery: {average_cost_wo_battery}")
print(f"Average cost with battery: {average_cost_with_battery}")
print(f"Average cost difference: {average_cost_difference}")

# ----------------------------------------------------------------
# 3.2 analyse consistency of battery charge and discharge decision
plt.figure(figsize=(12, 6))

# Iterate through each sample in the result_df
for index, row in result_df.iterrows():
    sample_number = row['sample']
    
    # Extract y2td values for each time step
    y2td_values = [row['time_steps'][t]['y2td'] for t in range(T)]

    # Plot the scatter points for y2td
    plt.scatter(range(T), y2td_values, label=f'Sample {sample_number + 1} - y2td', alpha=0.5)

# Set labels and title
plt.xlabel('Time Step')
plt.ylabel('y2td Value')
plt.title(f'Scatter Plot of discharge decision Against Time Step for {sample_number+1} Sample')

# Show legend
plt.legend(loc='upper center', bbox_to_anchor=(0.5, -0.2), fancybox=True, shadow=True, ncol=2)

# Show the plot
plt.show()

for index, row in result_df.iterrows():
    sample_number = row['sample']
    
    # Extract y2td values for each time step
    y2tch_values = [row['time_steps'][t]['y2tch'] for t in range(T)]

    # Plot the scatter points for y2td
    plt.scatter(range(T), y2tch_values, label=f'Sample {sample_number + 1} - y2tch', alpha=0.5)

# Set labels and title
plt.xlabel('Time Step')
plt.ylabel('y2td Value')
plt.title(f'Scatter Plot of discharge decision Against Time Step for {sample_number+1} Sample')

# Show legend
plt.legend(loc='upper center', bbox_to_anchor=(0.5, -0.2), fancybox=True, shadow=True, ncol=2)

# Show the plot
plt.show()
