import math

import numpy as np
import pandas as pd
import csv

output_file_path = 'data/m3_dp_resell_48.csv'

# Constants and Inputs
T = 48  # Total number of hours
# single_battery_capacity = 150  # battery capacity in kWh
# consumption_std_dev = 9.86
# demand = np.random.normal(111.87, consumption_std_dev, 24)
demand = [111.87 * 0.5 for i in range(T)]
minimum_battery_support_hours = 1   # one hour

# number_of_battery = math.ceil(111.87 * minimum_battery_support_hours / single_battery_capacity)
number_of_battery = 1
battery_capacity = 150 * number_of_battery

battery_cost = 16.93 # per day
total_battery_cost = battery_cost*number_of_battery  # per day

# technician_cost = 89.4  # /kWh

df = pd.read_csv('data/USEP_08Nov2023.csv')
prices = df['USEP ($/MWh)'].tolist()

for i in range(len(prices)):
    prices[i] = prices[i] / 1000

# Memoization Table
memo = {}

def find_min_cost(t, battery_level):
    # Base case: end of the time horizon
    if t == T:
        return 0, [], []

    # Check if the state has been computed before
    if (t, battery_level) in memo:
        return memo[(t, battery_level)]

    # Decision 1: Charge the battery by 50%
    cost_charge = battery_capacity * prices[t]
    new_battery_level_charge = min(battery_level + battery_capacity, battery_capacity)
    future_cost_charge, future_decisions_charge, future_charge_level = find_min_cost(t + 1, new_battery_level_charge)
    total_cost_charge = cost_charge + demand[t] * prices[t] + future_cost_charge

    # Decision 2: Discharge all from the battery
    discharge_amount = min(battery_level, demand[t])
    resell_amount = battery_level - discharge_amount
    new_battery_level_discharge = 0
    future_cost_discharge, future_decisions_discharge, future_discharge_level = find_min_cost(t + 1, new_battery_level_discharge)
    total_cost_discharge = (demand[t] - discharge_amount) * prices[t] + future_cost_discharge - resell_amount * prices[t] * 0.9

    # Decision 3: Do nothing
    future_cost_do_nothing, future_decisions_do_nothing, future_do_nothing_level = find_min_cost(t + 1, battery_level)
    total_cost_do_nothing = demand[t] * prices[t] + future_cost_do_nothing

    target = min(total_cost_do_nothing, total_cost_charge, total_cost_discharge)
    if target == total_cost_do_nothing:
        memo[(t, battery_level)] = (total_cost_do_nothing, ["Do Nothing"] + future_decisions_do_nothing, [battery_level] + future_do_nothing_level)
    elif target == total_cost_charge:
        memo[(t, battery_level)] = (total_cost_charge, ["Charge"] + future_decisions_charge, [new_battery_level_charge] + future_charge_level)
    else:
        memo[(t, battery_level)] = (total_cost_discharge, ["Discharge"] + future_decisions_discharge, [new_battery_level_discharge] + future_discharge_level)

    return memo[(t, battery_level)]

# Compute the optimal decisions
min_cost, optimal_decisions, battery_level = find_min_cost(0, 0)

# Output
for i in range(len(optimal_decisions)):
    print(f"Decision {i}: {optimal_decisions[i]} battery level {battery_level[i]}")
print("Total Cost:", min_cost + total_battery_cost)

original_cost = 0
for i in range(T):
    original_cost += (demand[i] * prices[i])
print("Origin Cost:", original_cost)

# write data in csv
with open(output_file_path, mode='w', newline='') as csv_file:
    writer = csv.writer(csv_file)

    # Write header
    header = ['Time', 'Electricity Price', 'Battery Power', 'Battery Decision']
    writer.writerow(header)

    # Write data
    for i in range(len(optimal_decisions)):
        row = [i, prices[i], battery_level[i], optimal_decisions[i]]
        writer.writerow(row)