import csv
from datetime import datetime

def save_to_csv(data):
    now = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"historico_{now}.csv"

    with open(filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=["name", "symbol", "price", "market_cap", "volume"])
        writer.writeheader()
        for row in data:
            writer.writerow(row)

    return filename
