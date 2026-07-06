# X Account Monitor

Collects new posts from one X account, stores them in SQLite, and syncs the database to Google Drive. It is designed to run as a Google Cloud Run Job every 12 hours.

Default target:

```text
@aleabitoreddit
```

The collector uses the official X API user timeline endpoint. It fetches posts authored by the target account, including replies written by that account. It does not collect replies written by other users.

## What It Does

Every run:

1. Downloads `aleabitoreddit.sqlite` from Google Drive, if Drive sync is configured.
2. Looks up the target X account.
3. Fetches posts newer than the latest saved post ID.
4. Saves new posts to SQLite.
5. Uploads the updated SQLite database back to Google Drive.

No AI summarization is used in this version.

## Local Files

```text
x_account_monitor/
  Dockerfile
  requirements.txt
  .env.example
  x_account_monitor/
    main.py
    x_client.py
    storage.py
    drive_sync.py
    config.py
```

## Required Accounts And Keys

You need:

- X Developer Platform bearer token
- Google Cloud project with billing enabled
- Google Drive folder for persisted files

Google Cloud should be very cheap for this workload. The expected Google Cloud cost is usually close to `$0/month` for one Cloud Run Job triggered every 12 hours, though billing must be enabled and misconfiguration can create small charges.

## Environment Variables

Copy `.env.example` and fill in values for local testing.

Required:

```text
TARGET_USERNAME=aleabitoreddit
X_BEARER_TOKEN=...
```

For Google Drive sync:

```text
GOOGLE_DRIVE_FOLDER_ID=...
```

On Cloud Run, leave these blank and use Application Default Credentials:

```text
GOOGLE_SERVICE_ACCOUNT_JSON=
GOOGLE_APPLICATION_CREDENTIALS=
```

Then share the Google Drive folder with the Cloud Run runtime service account email.

## Local Test

From this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
$env:TARGET_USERNAME="aleabitoreddit"
$env:X_BEARER_TOKEN="..."
$env:WORK_DIR="$PWD\data"
python -m x_account_monitor
```

Without `GOOGLE_DRIVE_FOLDER_ID`, the app writes only to the local work directory.

On Windows, the default `WORK_DIR=/tmp/x_account_monitor` is not ideal. For local testing, set:

```powershell
$env:WORK_DIR="$PWD\data"
```

## Google Cloud Setup

Set shell variables:

```bash
PROJECT_ID="your-project-id"
REGION="us-central1"
REPOSITORY="x-account-monitor"
JOB_NAME="x-account-monitor"
RUNTIME_SA="x-account-monitor-runner@$PROJECT_ID.iam.gserviceaccount.com"
SCHEDULER_SA="x-account-monitor-scheduler@$PROJECT_ID.iam.gserviceaccount.com"
```

Enable APIs:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  drive.googleapis.com
```

Create service accounts:

```bash
gcloud iam service-accounts create x-account-monitor-runner \
  --display-name="X Account Monitor Runner"

gcloud iam service-accounts create x-account-monitor-scheduler \
  --display-name="X Account Monitor Scheduler"
```

Share your Google Drive folder with:

```text
x-account-monitor-runner@your-project-id.iam.gserviceaccount.com
```

Create the X bearer token secret:

```bash
printf "%s" "your-x-bearer-token" | gcloud secrets create x-bearer-token --data-file=-
```

Allow the runtime service account to read secrets:

```bash
gcloud secrets add-iam-policy-binding x-bearer-token \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/secretmanager.secretAccessor"
```

Create an Artifact Registry repository:

```bash
gcloud artifacts repositories create "$REPOSITORY" \
  --repository-format=docker \
  --location="$REGION"
```

Build and push the container:

```bash
gcloud builds submit \
  --tag "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$JOB_NAME:latest"
```

Create the Cloud Run Job:

```bash
gcloud run jobs create "$JOB_NAME" \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$JOB_NAME:latest" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --set-env-vars "TARGET_USERNAME=aleabitoreddit,GOOGLE_DRIVE_FOLDER_ID=your-drive-folder-id" \
  --set-secrets "X_BEARER_TOKEN=x-bearer-token:latest" \
  --max-retries 1 \
  --task-timeout 10m
```

Run it manually once:

```bash
gcloud run jobs execute "$JOB_NAME" --region "$REGION" --wait
```

Allow the scheduler service account to run the job:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SCHEDULER_SA" \
  --role="roles/run.developer"
```

Create a 12-hour Cloud Scheduler trigger:

```bash
gcloud scheduler jobs create http x-account-monitor-12h \
  --location "$REGION" \
  --schedule "0 */12 * * *" \
  --uri "https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/$JOB_NAME:run" \
  --http-method POST \
  --oauth-service-account-email "$SCHEDULER_SA"
```

## SQLite Schema

Tables:

- `accounts`
- `posts`
- `runs`

The `posts` table stores the raw X API JSON, so future fields can be recovered without refetching old posts.

## Notes

- `EXCLUDE_RETWEETS=true` by default.
- Replies are included only when authored by the monitored account.
- If no new posts are found, the run records `new_post_count = 0`.
- If a run fails after creating a Drive lock file, delete `x_account_monitor.lock` from the Drive folder before the next run.
