import requests
import json
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

url = 'http://localhost:6006/data/plugin/scalars/scalars?run=.&tag=RMSE'

response = requests.get(url)

if response.ok:
    json_data = json.loads(response.content)
    df = pd.DataFrame(json_data, columns=["walltime", "iteration", "value"])


    fig, axs = plt.subplots(1, 1)

    axs.plot(df["iteration"], df["value"])
    fig.savefig("rmse.png")

    last_value = df["value"].tail(1)

    from IPython import embed
    embed()
