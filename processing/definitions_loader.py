import pandas as pd

def load_definitions(path):
    df = pd.read_csv(path)
    return df
