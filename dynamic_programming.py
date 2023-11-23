import math

import numpy as np

from price_calculator import get_price_list

# Constants and Inputs
T = 24  # Total number of hours
single_battery_capacity = 150  # battery capacity in kWh
consumption_std_dev = 9.86
demand = np.random.normal(111.87, consumption_std_dev, 24)
number_of_battery = math.ceil(111.87 / single_battery_capacity)
battery_capacity = 150 * number_of_battery

battery_cost = 1.41  # /kWh
technician_cost = 89.4  # /kWh

prices = get_price_list('./data/USEP_08Nov2023_to_14Nov2023.csv')
for i in range(len(prices)):
    prices[i] = prices[i] / 1000

# Memoization Table
memo = {}

def find_min_cost(t, battery_level):
    # Base case: end of the time horizon
    if t == T:
        return 0, []

    # Check if the state has been computed before
    if (t, battery_level) in memo:
        return memo[(t, battery_level)]

    # Decision 1: Charge the battery by 50%
    cost_charge = 0.5 * battery_capacity * prices[t]
    new_battery_level_charge = min(battery_level + 0.5 * battery_capacity, battery_capacity)
    future_cost_charge, future_decisions_charge = find_min_cost(t + 1, new_battery_level_charge)
    total_cost_charge = cost_charge + demand[t] * prices[t] + future_cost_charge + battery_cost + technician_cost

    # Decision 2: Discharge all from the battery
    discharge_amount = min(battery_level, demand[t])
    new_battery_level_discharge = max(battery_level - discharge_amount, 0)
    future_cost_discharge, future_decisions_discharge = find_min_cost(t + 1, new_battery_level_discharge)
    total_cost_discharge = (demand[t] - discharge_amount) * prices[t] + future_cost_discharge + battery_cost + technician_cost

    # Choose the decision with minimum cost
    if total_cost_charge < total_cost_discharge:
        memo[(t, battery_level)] = (total_cost_charge, ["Charge"] + future_decisions_charge)
    else:
        memo[(t, battery_level)] = (total_cost_discharge, ["Discharge"] + future_decisions_discharge)

    return memo[(t, battery_level)]

# Compute the optimal decisions
min_cost, optimal_decisions = find_min_cost(0, 0)

# Output
print("Optimal Decisions:", optimal_decisions)
print("Total Cost:", min_cost)

original_cost = 0
for i in range(T):
    original_cost += (demand[i] * prices[i] + battery_cost + technician_cost)
print("Origin Cost:", original_cost)
