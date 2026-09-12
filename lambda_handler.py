from mangum import Mangum

from src.api.monitor_api import app

handler = Mangum(app, lifespan="off")
