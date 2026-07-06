# Project Record

Goal: monitor all posts from `@aleabitoreddit` on X, including original posts and replies written by the account owner only. Store the posts and run the collector every 12 hours.

Chosen v1 architecture:

```text
Cloud Scheduler
  every 12 hours
Cloud Run Job
  Python collector
X API
  user timeline polling
SQLite
  post database
Google Drive
  persistent file storage
```

Why polling:

The desired collection cadence is every 12 hours, so X API timeline polling is simpler than Activity API streaming. Streaming can be added later if near-real-time capture becomes important.

Why SQLite:

SQLite is free, requires no server, and works well as a single database file for one scheduled writer. Google Drive is used as persistent storage between Cloud Run executions.

What is collected:

- Original posts from the target account
- Replies written by the target account
- Quote posts
- Reposts only if `EXCLUDE_RETWEETS=false`

What is not collected:

- Replies from other users
- Browser-scraped data
- AI summaries

Delivery/storage v1:

- Full history in `aleabitoreddit.sqlite`
- Run history in the SQLite `runs` table
