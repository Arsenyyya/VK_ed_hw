"""One-time official httpfs installation, outside the measured runs."""
import duckdb
from common import ROOT

con = duckdb.connect()
con.execute("SET extension_directory = ?", [str(ROOT / ".cache/extensions")])
con.execute("INSTALL httpfs")
con.execute("LOAD httpfs")
print("DuckDB", duckdb.__version__, "httpfs installed")
