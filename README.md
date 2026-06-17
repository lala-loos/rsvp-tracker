# RSVP Tracker

A lightweight Python/Flask app to track who clicked your email RSVP button.

## How it works

1. You add guests via the API (name + email + a unique ID)
2. Each guest gets a unique link: `https://yoursite.com/rsvp/jane123`
3. You put that link as the button URL in their email
4. When they click → the server logs it → you see it on the dashboard

---

## Setup (Local)

```bash
pip install -r requirements.txt
python app.py
```

Visit `http://localhost:5000` for the dashboard.

---

## Adding Guests

Send a POST request for each guest:

```bash
curl -X POST http://localhost:5000/admin/add-guest \
  -H "Content-Type: application/json" \
  -d '{"id": "jane123", "name": "Jane Smith", "email": "jane@example.com"}'
```

Response:
```json
{
  "success": true,
  "rsvp_link": "/rsvp/jane123"
}
```

Use a script to bulk-add from a CSV — see below.

---

## Bulk Import from CSV

Create a `guests.csv` like:
```
id,name,email
jane123,Jane Smith,jane@example.com
bob456,Bob Jones,bob@example.com
```

Then run:
```python
import csv, requests, uuid

with open("guests.csv") as f:
    for row in csv.DictReader(f):
        r = requests.post("http://localhost:5000/admin/add-guest", json=row)
        print(row["name"], r.json())
```

---

## Email Button

In your email, make the "Yes, I'm coming!" button link to:
```
https://yoursite.com/rsvp/jane123
```

Each guest gets their own unique link. When clicked, they're redirected to `/confirmed`
(or any URL you set via the `REDIRECT_URL` environment variable).

---

## Deploy to Railway

1. Push this folder to a GitHub repo
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Set start command: `python app.py`
4. Done — Railway gives you a public URL

Optional: set `REDIRECT_URL` env var to redirect guests to your own page after clicking.

---

## Dashboard

Visit `/` to see:
- How many guests you invited
- How many have clicked (responded)
- Who clicked and when
- Individual RSVP links per guest
