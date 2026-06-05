# captions-web-app

Lightweight Flask + React/Vite app for the acoustic captioning study.

## Docker deployment via AWS ECR  
```bash 
aws ecr create-repository --repository-name acoustic-captions-survey
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
docker build -t acoustic-captions-survey -f Dockerfile .
docker tag acoustic-captions-survey:latest <account-id>.dkr.ecr.<region>.amazonaws.com/acoustic-captions-survey:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/acoustic-captions-survey:latest
```

### App Runner Command 
```bash
aws apprunner create-service \
  --service-name acoustic-captions-survey \
  --source-configuration '{
    "ImageRepository": {
      "ImageIdentifier": "<account-id>.dkr.ecr.<region>.amazonaws.com/acoustic-captions-survey:latest",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "5000",
        "RuntimeEnvironmentVariables": {
          "STEP_1_TRIALS":"5",
          "STEP_2_TRIALS":"5",
          "STEP_3_TRIALS":"5"
        }
      }
    },
    "AutoDeploymentsEnabled": true
  }'
```

## Docker dpeloyment via Azure Cloud 
```bash
az group create -n rg-acoustic-captions -l <region>
az acr create -n <acrName> -g rg-acoustic-captions --sku Basic
az acr build -r <acrName> -t acoustic-captions-survey:latest -f Dockerfile .
```

### Container Apps Environment 
```bash 
az containerapp env create -n cae-acoustic-captions -g rg-acoustic-captions -l <region>

az containerapp create \
  -n ca-acoustic-captions \
  -g rg-acoustic-captions \
  --environment cae-acoustic-captions \
  --image <acrName>.azurecr.io/acoustic-captions-survey:latest \
  --target-port 5000 \
  --ingress external \
  --registry-server <acrName>.azurecr.io \
  --query properties.configuration.ingress.fqdn
```
### Set runtime env vars
```bash
az containerapp update \
  -n ca-acoustic-captions \
  -g rg-acoustic-captions \
  --set-env-vars STEP_1_TRIALS=5 STEP_2_TRIALS=5 STEP_3_TRIALS=5
``` 

## Notes 

- Do not bake .env into the image.

- Set `GOOGLE_SHEETS_ID` and `GOOGLE_SERVICE_ACCOUNT_JSON` in cloud environment settings/secrets.

- If you want React hosted from the same domain, deploy frontend separately as static hosting: 
   - S3 plus CloudFront on AWS, or Azure Static Web Apps on Azure.

- Keep API base URL relative on the frontend when possible to avoid CORS complexity.

## Google Sheets setup

1. Create a Google Cloud project.
2. Enable the Google Sheets API.
3. Create a service account for the app.
4. Generate a JSON key file for that service account.
5. Open the target Google Sheet and share it with the service-account email address with Editor access.
6. Copy the spreadsheet ID from the Google Sheets URL and set `GOOGLE_SHEETS_ID`.
7. Set `GOOGLE_SERVICE_ACCOUNT_JSON` to either:
   - the raw JSON contents, or
   - the path to the downloaded key file.

The backend will append rows to the worksheet named by `GOOGLE_SHEETS_WORKSHEET` and will fall back to `captions-web-app/submissions.csv` if Sheets is not configured.

## Local development

1. Copy `.env.example` to `.env` and fill in any values you need.
2. Install frontend dependencies:

```bash
cd captions-web-app
npm install
```

3. Install backend dependencies:

```bash
python3 -m pip install -r captions-web-app/requirements.txt
```

4. Start the Flask backend:

```bash
cd captions-web-app
python3 app.py
```

5. Start the React frontend in a second terminal:

```bash
cd captions-web-app
npm run dev
```

6. Open the Vite URL shown in the terminal, usually `http://localhost:5173`.


## Docker Deployment 
1. Create Docker Image 
```
$ docker build -t acoustic-captions-survey -f Dockerfile . 
``` 

2. Start Docker container from Image. 
```
$ docker run -d -p 8080:8080 \
  -v /Users/jonathanferraro/Documents/Code/captions-web-app/gcp-keys.json:/app/secrets/gcp-keys.json \
  --env-file .env \
  --name container-test \
  acoustic-captions-survey
```

## Notes

- The frontend proxies `/api`, `/audio`, and `/files` to the Flask backend during local development.
- Study media is served directly from the repository, so the PDF and WAV files stay in place under the workspace.


captions-web-app/
├─ app.py
├─ index.html
├─ package.json
├─ README.md
├─ requirements.txt
├─ template_spreadsheet.csv
├─ vite.config.js
└─ src/
  ├─ App.jsx
  ├─ main.jsx
  └─ styles.css