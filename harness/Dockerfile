# Reproducible core for MESAS Paper 1 (LLM-assisted ISR swarm compositional RV).
# The headline result is stdlib-only Python -> no external services needed.
#   docker build -t swarm-rv .
#   docker run --rm swarm-rv                 # prints the headline table
FROM python:3.12-slim
WORKDIR /app
COPY swarm_rv.py run_demo.py experiments.py experiments_extra.py \
     experiments_advanced.py experiments_hierarchy.py experiments_properties.py \
     llm_loop.py rule_based_planner.py e2e_latency.py threat_sweep.py ./
# default = headline demo; run the full suites with:
#   docker run --rm swarm-rv python3 experiments.py
#   docker run --rm swarm-rv python3 experiments_extra.py
#   docker run --rm swarm-rv python3 experiments_advanced.py
#   docker run --rm swarm-rv python3 experiments_hierarchy.py
#   docker run --rm swarm-rv python3 threat_sweep.py
# (swarm_to_monpoly.py runs on the HOST, not in this image — it drives the rvhier image.)
ENTRYPOINT []
CMD ["python3", "run_demo.py", "--md"]
