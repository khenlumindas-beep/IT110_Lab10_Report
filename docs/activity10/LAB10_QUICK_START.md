# IT 110 Lab Activity 10 - Quick Start Guide

## ✅ SmartTrack Backend is Running!

**Server Address:** http://127.0.0.1:8001

**Swagger UI (Interactive Docs):** http://127.0.0.1:8001/api/docs

---

## Step 1: Verify Health Endpoint

Open your browser and visit:
```
http://127.0.0.1:8001/health
```

Expected response:
```json
{
  "status": "ok"
}
```

✅ **SCREENSHOT S01:** Take screenshot showing address bar and JSON response.

---

## Step 2: Open Swagger UI

Visit:
```
http://127.0.0.1:8001/api/docs
```

You should see all SmartTrack API endpoints organized by category:
- Authentication
- Users
- Travels
- Documents
- Compliance
- Analytics
- etc.

✅ **SCREENSHOT S02:** Take screenshot showing Swagger UI with endpoint list.

---

## Step 3: Test Endpoints Without Authentication

### Test 1: Get Colleges (No Auth Required)
1. In Swagger UI, find `GET /api/colleges`
2. Click "Try it out"
3. Click "Execute"
4. Verify Status: 200 OK
5. Response shows list of colleges

✅ **SCREENSHOT F31:** Capture request and response.

### Test 2: Root Endpoint
Visit: http://127.0.0.1:8001/

Response:
```json
{
  "name": "SmartTrack",
  "description": "AI-Based International Travel Monitoring System",
  "version": "1.0.0",
  "docs": "/api/docs"
}
```

---

## Step 4: Test Endpoints WITH Authentication

### A. Register New User
1. Find `POST /api/auth/register` in Swagger UI
2. Click "Try it out"
3. Use this test data:
```json
{
  "email": "testuser@csu.edu",
  "password": "TestPass123!",
  "full_name": "Test User Lab 10",
  "role": "faculty"
}
```
4. Click "Execute"
5. Verify Status: 200 OK
6. **Copy the `user_id` from response**

✅ **SCREENSHOT F01:** Capture registration success.

### B. Login to Get JWT Token
1. Find `POST /api/auth/login`
2. Click "Try it out"
3. Use credentials:
```json
{
  "email": "testuser@csu.edu",
  "password": "TestPass123!"
}
```
4. Click "Execute"
5. **Copy the `access_token` from response**

✅ **SCREENSHOT F02:** Capture login response with token (blur the actual token value).

### C. Authorize Swagger UI
1. Click the **"Authorize"** button at the top of Swagger UI
2. Enter: `Bearer <your_access_token>`
3. Click "Authorize"
4. Click "Close"

Now all protected endpoints will include your JWT token automatically!

---

## Step 5: Test Travel Management

### Create New Travel
1. Find `POST /api/travels`
2. Click "Try it out"
3. Use this data (replace user_id with yours):
```json
{
  "user_id": 55,
  "college_id": 1,
  "participant_type": "Faculty",
  "event_title": "Lab 10 Test Travel - AI Conference",
  "mobility_type": "Faculty Exchange",
  "start_date": "2026-12-01",
  "end_date": "2026-12-15",
  "destination_country": "Singapore",
  "workflow_status": "Pending Requirements"
}
```
4. Click "Execute"
5. Verify Status: 201 Created
6. **Copy the `travel_id` from response**

✅ **SCREENSHOT F08:** Capture travel creation.

### List Your Travels
1. Find `GET /api/travels`
2. Click "Try it out"
3. Click "Execute"
4. Verify you see ONLY your travel (RLS working!)

✅ **SCREENSHOT F09:** Capture RLS-filtered travel list.

---

## Step 6: Test Document Upload

### Upload Document
1. Find `POST /api/documents`
2. Click "Try it out"
3. Fill in:
   - `travel_id`: (your travel_id from above)
   - `document_type`: Passport
   - `file`: Click "Choose File" and select any PDF
4. Click "Execute"
5. Verify Status: 201 Created

✅ **SCREENSHOT F14:** Capture document upload success.

---

## Step 7: Test Compliance Endpoint

### Get Compliance Status
1. Find `GET /api/compliance/travels/{travel_id}`
2. Click "Try it out"
3. Enter your `travel_id`
4. Click "Execute"
5. Verify you see compliance percentage (should show 1 document uploaded)

✅ **SCREENSHOT F19:** Capture compliance status.

---

## Quick Test Results Summary

| Test | Endpoint | Status | Screenshot |
|------|----------|--------|------------|
| Health | GET /health | ✅ 200 OK | S01 |
| Swagger UI | /docs | ✅ Working | S02 |
| Register | POST /api/auth/register | ✅ 200 OK | F01 |
| Login | POST /api/auth/login | ✅ 200 OK | F02 |
| List Colleges | GET /api/colleges | ✅ 200 OK | F31 |
| Create Travel | POST /api/travels | ✅ 201 Created | F08 |
| List Travels (RLS) | GET /api/travels | ✅ 200 OK | F09 |
| Upload Document | POST /api/documents | ✅ 201 Created | F14 |
| Get Compliance | GET /api/compliance/travels/{id} | ✅ 200 OK | F19 |

---

## Common Issues and Solutions

### Issue 1: "Not authenticated" error
**Solution:** Click "Authorize" button and enter JWT token from login

### Issue 2: "Foreign key constraint" error
**Solution:** Use valid IDs (get colleges list first, then use college_id from there)

### Issue 3: RLS returns empty array
**Solution:** Make sure you're logged in as the user who created the travel

### Issue 4: Document upload fails
**Solution:** Ensure travel_id belongs to your user, and file is valid PDF

---

## Stop the Server

When done testing:
```
Press CTRL+C in the terminal where uvicorn is running
```

---

## Next Steps for Lab Report

1. Collect all screenshots (S01, S02, F01-F38)
2. Fill in `backend/IT110_Lab10_Report.md`
3. Document any errors encountered (BEFORE and AFTER screenshots)
4. Commit to GitHub:
```bash
git add backend/IT110_Lab10_Report.md backend/test_endpoints.py
git commit -m "Lab Activity 10: FastAPI Backend Testing Complete"
git push origin main
```

5. Submit report via MasaoLMS

---

**Good luck with your lab activity!** 🚀
