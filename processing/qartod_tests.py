import yaml
from ioos_qc.config import Config
from ioos_qc.streams import PandasStream
from ioos_qc.results import collect_results

# 1) Load YAML 
with open(r"qc_config.yml", "r", encoding="utf-8") as f:
    qc_dict = yaml.safe_load(f)

cfg = Config(qc_dict)              # modern, non-deprecated entry point  (docs)  # [2](https://ioos.github.io/ioos_qc/)
stream = PandasStream(df)          # df is indexed by time; columns: temperature, salinity, ...

# 2) Run ALL configured packages/tests on the stream 
results = stream.run(cfg)         
# 3) Normalize the list of results into convenient objects
collected = collect_results(results)   # gives CallResult/ContextResult with .test, .variable, .results  

# 4) Materialize per-test columns (QARTOD flags: 1,2,3,4,9)
for r in collected:
    # r.variable is the variable name from YAML (e.g., "temperature")
    # r.test is the test name (e.g., "gross_range_test")
    df[f"{r.variable}__{r.test}"] = r.results
