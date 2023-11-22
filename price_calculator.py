import pandas as pd


def get_price_list(file_path):
    power_prices_data = pd.read_csv(file_path)

    power_prices_data.head()

    # Creating a helper column for grouping by every two half-hour periods
    power_prices_data['Hour_Group'] = (power_prices_data['PERIOD'] - 1) // 2

    # Grouping by date and Hour_Group, then calculating the average USEP for each hour
    hourly_avg_prices_corrected = power_prices_data.groupby(['DATE', 'Hour_Group'])['USEP ($/MWh)'].mean().reset_index()

    # Rename columns for clarity
    hourly_avg_prices_corrected.rename(columns={'Hour_Group': 'Hour', 'USEP ($/MWh)': 'Average_USEP'}, inplace=True)

    # Display the first few rows of the corrected aggregated data
    hourly_avg_prices_corrected.head()

    # Grouping by the hour and calculating the average USEP across all days
    average_hourly_price = hourly_avg_prices_corrected.groupby('Hour')['Average_USEP'].mean().reset_index()

    ctb_list = average_hourly_price['Average_USEP'].tolist()
    return ctb_list
