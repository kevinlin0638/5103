from gurobipy import Model, GRB
import pandas as pd
import numpy as np
import json

from sklearn.metrics import mean_squared_error as mse

# 1. Global Parameter

# 1.1 Time
T = 48 # 1 day, every 30 minutes

# 1.2 Price ($/MWh)
# Price forecast, as nominal
forecast_price = pd.read_csv('./data/USEP_08Nov2023_to_14Nov2023.csv')
price_nominal = forecast_price['USEP ($/MWh)'].tolist()

# Use historical data to calculate the RMSE of the price forecast, as deviation
historical_price = pd.read_csv('./data/WEP_10Oct2023_to_09Nov2023.csv')
actual_price= historical_price['WEP ($/MWh)']
predicted_price =historical_price['USEP ($/MWh)']
price_rmse= mse(actual_price, predicted_price, squared=False)
print(f'The forecast model error is: {price_rmse: .2f} $/MWh')

selling_price_discount = 0.9

# 1.3 Demand in kwh
Ed = 111.87 * 0.5

# 1.4 Battery
number_of_battery = 1
battery_cost = 11.35 # per day
DC_AC_efficiency = 0.94

total_battery_cost = battery_cost*number_of_battery  # per day

single_battery_capacity_kwh = 150 # Battery capacity is fixed
Beta_max = single_battery_capacity_kwh * number_of_battery  # maximum battery capacity (define this)

# 1.5 Sample size
sample_size = 1000

# ----------------------------------------------------------------

# 2. Model Setup

def model_price_error_setup():

    model = Model("Price Forecast Error")

    # Set parameters
    prices = np.random.normal(price_nominal, price_rmse, T)
    cost_wo_battery = sum(Ed * (price/1000) for price in prices)

    # Add variables

    E = model.addVars(3, 3, T, name="E")  # Energy variables Eijt
    y2tch = model.addVars(T, vtype=GRB.BINARY, name="y2tch")  # Binary variables for ESS charge state
    y2td = model.addVars(T, vtype=GRB.BINARY, name="y2td")  # Binary variables for ESS discharge state
    battery_power = model.addVars(T, name="battery_power")  # Current power of ESS

    # Set objective function

    model.setObjective(sum((prices[t]/1000) * (E[0, 2, t] + E[0, 1, t])
                        - selling_price_discount * (prices[t]/1000) * E[1, 0, t] for t in range(T))
                        + total_battery_cost
                        , GRB.MINIMIZE)

    # Add constraints

    # Fulfill load demand
    model.addConstrs((E[0, 2, t] + E[1, 2, t] == Ed for t in range(T)), "LoadDemand")

    # ESS does not charge and discharge simultaneously
    model.addConstrs((y2tch[t] + y2td[t] <= 1 for t in range(T)), "ChargeDischarge")

    # ESS discharge does not exceed its current power
    model.addConstrs((E[1, 2, t] + E[1, 0, t] <= DC_AC_efficiency * battery_power[t] * y2td[t] for t in range(T)), "DischargeLimit")

    # ESS charge does not exceed what’s left
    model.addConstrs((DC_AC_efficiency * E[0, 1, t] <= (Beta_max - battery_power[t]) * y2tch[t] for t in range(T)), "ChargeLimit")
    model.addConstrs((DC_AC_efficiency * E[0, 1, t] <= Beta_max for t in range(T)), "ChargeLimit_2")

    # ESS power does not exceed its max capacity and is non-negative
    for t in range(T):
        model.addConstr(battery_power[t] >= 0, f"PowerLowerBound_{t}")
        model.addConstr(battery_power[t] <= Beta_max, f"PowerUpperBound_{t}")

    # ESS min charge/discharge 1MWh
    model.addConstrs((E[0, 1, t] >= y2tch[t] for t in range(T)), "ChargeConstraint")
    model.addConstrs((E[1, 2, t] >= y2td[t] for t in range(T)), "DischargeConstraint")

    # ESS current power is based on previous round power
    for t in range(1, T):
        model.addConstr(battery_power[t] == battery_power[t-1] - (E[1, 2, t-1] + E[1, 0, t-1]) * y2td[t-1] / DC_AC_efficiency +
                        DC_AC_efficiency * E[0, 1, t-1] * y2tch[t-1], "PowerUpdate")

    # Battery fully discharged at t=1
    model.addConstr(battery_power[0] == 0, "InitialDischarge")

    model.setParam( 'OutputFlag', False )

    return model, prices, cost_wo_battery, E, y2tch, y2td, battery_power

# ----------------------------------------------------------------

# 3. Model Run

result_all = []


for i in range(sample_size):

    result_sample = {'sample': i, 'cost_w/o_battery': 0, 'time_steps': {}}

    model, prices, cost_wo_battery, E, y2tch, y2td, battery_power = model_price_error_setup()
    model.optimize()

    if model.Status == GRB.OPTIMAL:
        result_sample['cost_w/o_battery'] = cost_wo_battery
        result_sample['cost_w_battery'] = model.objVal
        result_sample['cost_diff'] = cost_wo_battery - model.objVal

        for t in range (T):
            result_sample['time_steps'][t] = {
                'price': prices[t]/1000,
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
with open('./data/results_m3.json', 'w') as f:
    json.dump(result_all, f)

# ----------------------------------------------------------------

# 4. Result Analysis

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
