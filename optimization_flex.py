import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import optimize

# Read LV and MV aggregated demand // PV production // Price of electricity from the grid
# PV production
df_PV = pd.read_csv('pv_production.csv', index_col=0)
df_PV['time'] = pd.to_datetime(df_PV.index, dayfirst=True)
df_PV.index = df_PV['time']

# get he data for the reference weeks
df_PV_march = df_PV.loc['20160314':'20160321000000']
df_PV_june = df_PV.loc['20160606':'20160613000000']
df_PV_september = df_PV.loc['20160912':'20160919000000']
df_PV_december = df_PV.loc['20161205':'20161212000000']

pv_production_march = df_PV_march['PV production']
pv_production_june = df_PV_june['PV production']
pv_production_september = df_PV_september['PV production']
pv_production_december = df_PV_december['PV production']

pv_production = pd.concat([pv_production_march,
                           pv_production_june,
                           pv_production_september,
                           pv_production_december],
                          ignore_index=True)

# Demand
df_LV = pd.read_csv('community_demand.csv', index_col=0)
df_MV = pd.read_csv('MV_demand.csv', index_col=0)
df_MV['time'] = pd.to_datetime(df_MV.index, dayfirst=True)
df_MV.index = df_MV['time']

df_MV_march = df_MV.loc['20160314':'20160321']
df_MV_june = df_MV.loc['20160606':'20160613']
df_MV_september = df_MV.loc['20160912':'20160919']
df_MV_december = df_MV.loc['20161205':'20161212']

LV_consumption_winter = np.asarray(df_LV['final consumption winter'])
LV_consumption_summer = np.asarray(df_LV['final consumption winter'])   # need to create the summer consumption for LV
MV_consumption_march = np.asarray(df_MV_march['final consumption march'])
MV_consumption_june = np.asarray(df_MV_june['final consumption june'])
MV_consumption_september = np.asarray(df_MV_september['final consumption september'])
MV_consumption_december = np.asarray(df_MV_december['final consumption december'])

consumption_march = pd.Series(LV_consumption_winter + MV_consumption_march)
consumption_june = pd.Series(LV_consumption_summer + MV_consumption_june)
consumption_september = pd.Series(LV_consumption_summer + MV_consumption_september)
consumption_december = pd.Series(LV_consumption_winter + MV_consumption_december)

demand = pd.concat([consumption_march,
                    consumption_june,
                    consumption_september,
                    consumption_december],
                   ignore_index=True)

# Grid price
df_tariff_winter = pd.read_excel('tariff.xlsx', sheetname='Winter_week')
df_tariff_summer = pd.read_excel('tariff.xlsx', sheetname='Summer_week')

grid_price_winter = df_tariff_winter['Price']
grid_price_summer = df_tariff_summer['Price']

grid_price = pd.concat([grid_price_winter,
                        grid_price_summer,
                        grid_price_summer,
                        grid_price_winter],
                       ignore_index=True)

# Read flex consumption - EWH rated power = 4.5 kW
flex = pd.concat(4 * [df_LV['flex winter']], ignore_index=True)     # get the consumption from flexible assets
ewh_status = pd.concat(4 * [df_LV['63']], ignore_index=True)        # get the status of clustered ewh
ewh_n_status = pd.concat(4 * [df_LV.drop(df_LV.columns[[0, 1, 65]], axis=1)], ignore_index=True)

demand_flex = pd.Series(np.asarray(flex) + np.asarray(demand))
rated_power = 4.5
ewh_consumption_single = rated_power * .25  # consumption per period in kWh

# Need to get real value for PV system
LC = 100 / 52 * 4       # Price in euro/kW of PV installed per 1 week (1 year / 52 weeks) * 4 weeks (reference ones)
feed_in_tariff = 0      # should be set as the average price in the stock market times 0.90

# Start iteration to see the optimal number of PV to be installed
# Get the price of Scenario 1 - No PV installed
cost1 = 0

for i in range(672 * 4):
    cost1 = cost1 + demand_flex[i] * grid_price[i]

# Set up for the Scenario 2 - PV installed
n_set2 = 1
min_cost = cost1

cost2 = np.zeros(100)     # to keep track of the price variation
for j in range(100):    # See the price variations up to 100 PV systems
    PV = pv_production + j * pv_production
    for i in range(672 * 4):
        if (demand[i] + flex[i]) > PV[i]:
            cost2[j] = cost2[j] + (demand[i] + flex[i] - PV[i]) * grid_price[i]
        elif (demand[i] + flex[i]) <= PV[i]:
            cost2[j] = cost2[j] + (demand[i] + flex[i] - PV[i]) * feed_in_tariff

    cost2[j] = cost2[j] + (j + 1) * 5 * LC
    if cost2[j] < min_cost:
        min_cost = cost2[j]
        n_set2 = j + 1

# Set up Scenario 3 optimization with flexibility
cost3 = np.zeros(672 * 4)


def flex_cost(n_set3):
    for clock in range(672 * 4):
        # until there are flexible assets available try to get the demand lower than PV production
        while (demand[clock] + flex[clock]) > (n_set3 * pv_production[clock]) and (ewh_status[clock] > 0.0):
            print('Beginning of %d "While cycle"' % clock)
            print(ewh_status[clock])
            # check which ewh is available
            for ewh_n in range(63):
                # shift one ewh consumption slot (3 cases)
                if ewh_n_status.loc[clock][ewh_n] == 1 and clock != (672 * 4 - 4) and ewh_n_status.loc[clock+3][ewh_n] == 0:
                    ewh_n_status.loc[clock][ewh_n] -= 1
                    ewh_n_status.loc[clock+1][ewh_n] -= 1
                    ewh_n_status.loc[clock+2][ewh_n] -= 1
                    ewh_n_status.loc[clock+3][ewh_n] += 3
                    # fix the available flexibility
                    flex[clock] -= ewh_consumption_single
                    ewh_status[clock] -= 1
                    ewh_status[clock+3] += 1
                    break
                elif ewh_n_status.loc[clock][ewh_n] == 2 and clock != (672 * 4 - 3) and ewh_n_status.loc[clock+3][ewh_n] == 0:
                    ewh_n_status.loc[clock - 1][ewh_n] = 0
                    ewh_n_status.loc[clock][ewh_n] = 0
                    ewh_n_status.loc[clock + 1][ewh_n] = 1
                    ewh_n_status.loc[clock + 2][ewh_n] = 2
                    ewh_n_status.loc[clock + 3][ewh_n] = 3
                    # fix the available flexibility
                    flex[clock] -= ewh_consumption_single
                    ewh_status[clock-1] -= 1
                    ewh_status[clock] -= 1
                    ewh_status[clock+2] += 1
                    ewh_status[clock+3] += 1
                    break
                elif ewh_n_status.loc[clock][ewh_n] == 3 and clock != (672 * 4 - 2) and ewh_n_status.loc[clock+3][ewh_n] == 0:
                    ewh_n_status.loc[clock-2][ewh_n] = 0
                    ewh_n_status.loc[clock-1][ewh_n] = 0
                    ewh_n_status.loc[clock][ewh_n] = 0
                    ewh_n_status.loc[clock+1][ewh_n] = 1
                    ewh_n_status.loc[clock+2][ewh_n] = 2
                    ewh_n_status.loc[clock+3][ewh_n] = 3
                    # fix the available flexibility
                    flex[clock] -= ewh_consumption_single
                    ewh_status[clock - 2] -= 1
                    ewh_status[clock - 1] -= 1
                    ewh_status[clock] -= 1
                    ewh_status[clock + 2] += 1
                    ewh_status[clock + 3] += 1
                    break
        print('End of cycle %d' % clock)
        print(ewh_status[clock])
        if (demand[clock] + flex[clock]) > (n_set3 * pv_production[clock]):
            cost3[clock] = (demand[clock] + flex[clock] - n_set3 * pv_production[clock]) * grid_price[clock]
        elif (demand[clock] + flex[clock]) <= (n_set3 * pv_production[clock]):
            cost3[clock] = (demand[clock] + flex[clock] - n_set3 * pv_production[clock]) * feed_in_tariff
    return cost3.sum() + n_set3 * 5 * LC


print(cost2.min())
solution3 = optimize.fmin(flex_cost, 20)
print(solution3)