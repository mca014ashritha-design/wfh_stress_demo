# WFH Stress Prediction Demo

## Folder Structure

```text
wfh_stress_demo/
├── backend/
│   └── app.py
├── frontend/
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── css/
│       │   └── styles.css
│       └── js/
│           └── app.js
├── .env.example
├── README.md
└── requirements.txt
```

## Run in PowerShell

```powershell
cd "C:\Users\Ashritha\Downloads\wfh_stress_demo"
pip install -r requirements.txt

$env:MONGO_URI="mongodb://localhost:27017/"
$env:DB_NAME="wfh_stress_db"
$env:MODEL_PATH="../../wfh_final/tuned_model.pkl"
$env:FLASK_ENV="development"

python backend/app.py
```

Open this URL:

```text
http://localhost:5000/
```

MongoDB must be running locally before you submit the form. Your model file must exist at MODEL_PATH, or you can place tuned_model.pkl directly inside the backend folder.

## Email Alerts

To send weekly reports and high-stress alerts, set SMTP values before starting Flask.

Example for Gmail using an App Password:

```powershell
$env:SMTP_HOST="smtp.gmail.com"
$env:SMTP_PORT="587"
$env:SMTP_USER="your_email@gmail.com"
$env:SMTP_PASSWORD="your_app_password"
$env:SMTP_FROM="your_email@gmail.com"
$env:SMTP_USE_TLS="true"
```

If SMTP is not configured, the app still works. It will show that email was not sent.
