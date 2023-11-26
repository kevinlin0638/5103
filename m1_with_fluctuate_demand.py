import numpy as np
from gurobipy import Model, GRB
from price_calculator import get_price_list
import csv

output_file_path = 'data/m2_output_data_1h.csv'

model = Model("Optimization")

# 1. Parameter

# 1.1 Time
period = 1  # number of hours
T = int(24 / period)  # 1 day
# ($/MWh)

# 1.2 Price
ctb = get_price_list('data/USEP_08Nov2023.csv')
print('Prices:', ctb)

selling_price_discount = 0.9

# 1.3 Demand in kwh
np.random.seed(2023)
consumption_mean = 111.87
consumption_std_dev = 9.86
consumption = np.random.normal(consumption_mean, consumption_std_dev, T)
Ed = consumption.tolist()  # fixed load demand (define this)
cost_wo_battery = sum(x * y/1000 for x, y in zip(Ed, ctb))

# 1.4 Battery
number_of_battery = 1
battery_cost = 16.93 # per day

total_battery_cost = battery_cost*number_of_battery  # per day

single_battery_capacity = 150 # Battery capacity is fixed
Beta_max = single_battery_capacity * number_of_battery  # maximum battery capacity (define this)

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
model.addConstrs((E[1, 2, t] + E[1, 0, t] <= battery_power[t] * y2td[t] for t in range(T)), "DischargeLimit")

# ESS charge does not exceed what’s left
model.addConstrs((E[0, 1, t] <= (Beta_max - battery_power[t]) * y2tch[t] for t in range(T)), "ChargeLimit")
model.addConstrs((E[0, 1, t] <= Beta_max for t in range(T)), "ChargeLimit_2")

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

model.optimize()

if model.Status == GRB.OPTIMAL:
    print("Optimal solution found.")
elif model.Status == GRB.INFEASIBLE:
    print("Model is infeasible.")
elif model.Status == GRB.UNBOUNDED:
    print("Model is unbounded.")
else:
    print("Optimization ended with status:", model.Status)
print('--------------------------------------------------')
print(f"Average hourly power consumption: {Ed} kwh")
print(f"Number of battery: {number_of_battery}")
print(f"Total battery cost: ${total_battery_cost}")

print(f"Max battery capacity: {Beta_max} kWh")
print('--------------------------------------------------')
if model.Status == GRB.OPTIMAL:
    for t in range(T):
        label = ['Grid', 'ESS', 'Load']
        print(f"Time {t}: Electricity Price = {ctb[t]/1000} ,Battery Power = {battery_power[t].X}, ESS Charge = {y2tch[t].X}, ESS Discharge = {y2td[t].X}")
        for i in range(3):
            for j in range(3):
                if E[i, j, t].X != 0:
                    print(f"{label[i]} to {label[j]} at {t} = {E[i, j, t].X}")
        print('--------------------------------------------------')

print(f'Cost without battery: $ {cost_wo_battery}')
print(f'Cost with battery: $ {model.objVal}')
print(f'Cost difference: $ {cost_wo_battery - model.objVal}')

# write data in csv
with open(output_file_path, mode='w', newline='') as csv_file:
    writer = csv.writer(csv_file)

    # Write header
    header = ['Time', 'Electricity Price', 'Battery Power', 'ESS Charge', 'ESS Discharge']
    for i in range(3):
        for j in range(3):
            header.append(f'E[{i},{j}]')
    writer.writerow(header)

    # Write data
    for t in range(T):
        row = [t, ctb[t]/1000, battery_power[t].X, y2tch[t].X, y2td[t].X]
        for i in range(3):
            for j in range(3):
                row.append(E[i, j, t].X)
        writer.writerow(row)