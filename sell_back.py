from gurobipy import Model, GRB
from price_calculator import get_price_list

model = Model("Optimization")

period = 2  # number of hours
T = int(24 / period)  # 1 day
# ($/MWh)
prices = get_price_list('./data/USEP_29Oct2023_to_04Nov2023.csv')
print('Prices:', prices)
ctb = []
for i in range(0, len(prices), period):
    ctb.append(sum([prices[i] for i in range(i, i + period)]))

minimum_battery_support_hours = 1   # one hour
annual_electricity_consumption_gwh = 9
number_of_battery = 1
number_of_technician = 1  # number of technicians depending on the battery number
battery_cost = 2.05  # /kWh
technician_cost = 89.4  # /kWh


two_hours_in_year = 365 * 24 / period
average_hourly_consumption_gwh = annual_electricity_consumption_gwh / two_hours_in_year
average_hourly_consumption_kwh = average_hourly_consumption_gwh * 1000000
Ed = average_hourly_consumption_kwh  # fixed load demand (define this)
single_battery_capacity_kwh = average_hourly_consumption_kwh * minimum_battery_support_hours / period
Beta_max = single_battery_capacity_kwh * number_of_battery  # maximum battery capacity (define this)

# ----------------------------------------------------------------
E = model.addVars(3, 3, T, name="E")  # Energy variables Eijt
y2tch = model.addVars(T, vtype=GRB.BINARY, name="y2tch")  # Binary variables for ESS charge state
y2td = model.addVars(T, vtype=GRB.BINARY, name="y2td")  # Binary variables for ESS discharge state
battery_power = model.addVars(T, name="battery_power")  # Current power of ESS

# ----------------------------------------------------------------

model.setObjective(sum((ctb[t]/1000) * (E[0, 2, t] + E[0, 1, t]) +
                       battery_cost * number_of_battery * period +
                       technician_cost * number_of_technician * period -
                       0.8 * (ctb[t]/1000) * E[1, 0, t] for t in range(T)), GRB.MINIMIZE)

# ----------------------------------------------------------------
# Fulfill load demand
model.addConstrs((E[0, 2, t] + E[1, 2, t] == Ed for t in range(T)), "LoadDemand")

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
print(f"Annual power consumption: {average_hourly_consumption_gwh} GWh")
print(f"Minimum supported hours: {minimum_battery_support_hours}")
print(f"Number of battery: {number_of_battery}")
print(f"Battery cost: ${battery_cost}")
print(f"Number of technicians: {number_of_technician}")
print(f"Technician cost: ${technician_cost}")

print(f"Max battery capacity: {Beta_max} kWh")
print('--------------------------------------------------')
if model.Status == GRB.OPTIMAL:
    for t in range(T):
        label = ['Grid', 'ESS', 'Load']
        print(f"Time {t}: Battery Power = {battery_power[t].X}, ESS Charge = {y2tch[t].X}, ESS Discharge = {y2td[t].X}")
        for i in range(3):
            for j in range(3):
                if E[i, j, t].X != 0:
                    print(f"{label[i]} to {label[j]} at {t} = {E[i, j, t].X}")
        print('--------------------------------------------------')
