# Prostock: Indian Market Prediction & Trading Engine

> **⚠️ Study Note & Disclaimer:** This project has been built as a **hobby project** for educational purposes. Trading in financial markets involves significant risk. Use this software with extreme care. Always perform your own research and study before executing trades. The authors are not responsible for any financial losses.

![Prostock Dashboard](https://github.com/arulfrances/ProStock/blob/main/prostock-dashboard.png)

Prostock is an AI-powered trading application designed for the Indian market (Nifty 50, Bank Nifty, Sensex). It integrates data ingestion from NSE, feature engineering using technical indicators, ML-based prediction, and a broker-agnostic execution gateway.

## Project Structure

- `data/`: Raw and processed market data.
- `src/ingestion/`: Modules to fetch data from NSE/BSE and other APIs.
- `src/features/`: Feature engineering and technical indicators.
- `src/models/`: AI/ML model training and saved models.
- `src/execution/`: Broker API integrations (Zerodha, Upstox) and live strategy logic.
- `main_pipeline.py`: End-to-end ML pipeline (Fetch -> Feature -> Train).
- `src/execution/live_strategy.py`: Sample live trading loop with strategy logic.

## Getting Started

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Run ML Pipeline**:
    This will download historical Nifty 50 data, calculate indicators, and train an XGBoost model.
    ```bash
    python main_pipeline.py
    ```

3.  **Run Live Simulation**:
    This simulates a live price stream and executes a simple SMA crossover strategy.
    ```bash
    python src/execution/live_strategy.py
    ```

   ## 🚦 How to Start Your Engine:
# Step 1: Train the "Brain" (Takes ~10 seconds):

powershell
python main_pipeline.py
# Step 2: Start the Monitoring Station:

powershell
python src/api/monitor_api.py
Access your command center at http://localhost:8000.

# Step 3: Activate the Trading Bot:

powershell
python run_trading.py




## Features Implemented

- [x] **Data Ingestion**: Support for `yfinance` and NSE Bhavcopy downloading.
- [x] **Feature Store**: RSI, SMA, Volatility, and Lagged returns.
- [x] **Modeling**: XGBoost Classifier for price direction prediction.
- [x] **Execution**: Interface for Zerodha Kite and Upstox with order placement logic.
- [x] **Strategy**: Real-time ticker processing and signal generation.

![ProStock dashboard](https://github.com/arulfrances/ProStock/blob/main/prostock-dashboard.png)

## Future Roadmap

- [ ] Add deep learning models (LSTM/Transformers).
- [ ] Implement a full-fledged Backtest engine with slippage and costs.
- [ ] Create a monitoring dashboard using FastAPI & React/HTML.
- [ ] Integrate real-time WebSocket from Kite Connect/Upstox.

## Cloudflare Pages Dashboard

The dashboard can be deployed as a Cloudflare Pages static site. Its options panel presents
educational model observations for manual review; it does not place broker orders.

1. Deploy the FastAPI service separately on a public HTTPS URL and set
   `MARKET_API_BASE` in Cloudflare Pages to that URL (without a trailing slash).
2. In **Pages > Settings > Variables and Secrets**, add `MARKET_API_BASE`,
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and a long random `ALERT_API_KEY` as
   encrypted production and preview secrets. Enter `ALERT_API_KEY` in the dashboard
   Settings view when you want to send an alert; it is not saved after the browser
   session ends.
3. Deploy with:
   ```bash
   npx wrangler pages deploy src/api/static --project-name prostock
   ```

Cloudflare Pages automatically deploys the `functions/` directory. Telegram notifications are
only sent after a user selects **Send alert** in the dashboard and include a manual-review notice.

## AWS Lambda market API

The project includes a container-based Lambda deployment in `Dockerfile`, `lambda_handler.py`,
and `template.yaml`. Containers are used because the data and ML libraries are too large for a
reliable Lambda ZIP deployment. This API returns educational observations only and cannot place
broker orders.

## Keeping the Render deployment awake 24/7 (IST)

Render's free web service tier spins the dyno down after ~15 minutes without inbound traffic,
so the first request after idling can take 30-60s to "wake up". To keep
`prostock-market-api.onrender.com` responsive around the clock:

1. In this repo, go to **Settings > Secrets and variables > Actions** and add a secret named
   `RENDER_SERVICE_URL` with the value `https://prostock-market-api.onrender.com`.
2. The included workflow at `.github/workflows/keep-alive.yml` pings `/api/health` every 10
   minutes using GitHub Actions' scheduler, which prevents the free-tier dyno from idling.
3. `/api/health` is intentionally lightweight (no data download or model inference) so the
   pings don't add load or cost.

Notes:
- GitHub Actions cron schedules are best-effort and can lag a few minutes during high load;
  this is fine for keep-alive purposes but isn't a guaranteed uptime SLA.
- For a guaranteed always-on instance with no cold starts, upgrade the Render service to a
  paid plan (Starter or above), which doesn't sleep.
- You can also point any external uptime monitor (e.g., UptimeRobot, cron-job.org) at
  `/api/health` as an alternative or backup to the GitHub Action.


### Prerequisites

Install and authenticate the [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html),
[AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html),
and Docker Desktop. The AWS identity needs permission to create CloudFormation stacks, Lambda
functions, API Gateway HTTP APIs, IAM roles, ECR repositories, and CloudWatch logs.

```bash
aws configure
aws sts get-caller-identity
docker info
sam --version
```

### Deploy

From the repository root, validate, build, and deploy the API to the Mumbai region:

```bash
sam validate
sam build
sam deploy --guided --region ap-south-1
```

When prompted, choose a stack name such as `prostock-market-api`, allow SAM to create IAM roles,
and save the deployment settings. SAM creates the container repository, Lambda function, and API
Gateway HTTP API. At completion, copy the `MarketApiBase` output, then verify it:

```bash
curl "https://YOUR_API_ID.execute-api.ap-south-1.amazonaws.com/api/options-signals?symbol=NIFTY%2050"
```

Set that output as the `MARKET_API_BASE` secret in Cloudflare Pages, then redeploy the Pages
dashboard. The Lambda function uses `/tmp` for ephemeral cache files, so no market data or
review history is stored in Lambda.
