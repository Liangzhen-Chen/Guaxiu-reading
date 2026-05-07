# COS (Tencent Cloud Object Storage) Integration Plan

## Current State

- Books are stored **locally on disk** at `app/data/books/<book_id>/original.{epub,pdf,txt}`
- Upload happens via the `/api/books/upload` endpoint which reads the entire file into memory and writes it to disk on the ECS server
- COS service (`app/services/cos_service.py`) already implements three functions:
  - `get_presigned_upload()` -- generates a pre-signed PUT URL for frontend direct upload
  - `download_from_cos()` -- downloads a file from COS to local disk
  - `delete_from_cos()` -- deletes a file from COS
- The `/api/books/presign` and `/api/books/import-cos` endpoints already exist in `app/routers/books.py` but are **not wired into the frontend upload flow**

## Target Architecture

```
User selects file in browser
        |
        v
[Frontend] POST /api/books/presign  -->  gets upload_url, key
        |
        v
[Frontend] PUT file directly to COS using upload_url (pre-signed, 30min expiry)
        |
        v
[Frontend] POST /api/books/import-cos  { key, filename, title, author }
        |
        v
[Backend] Downloads file from COS to local disk
[Backend] Deletes COS temp object (cleanup)
[Backend] Creates DB record + triggers background parsing
```

## Benefits

1. **No server-side buffering**: Large files (up to 50MB) are uploaded directly to COS, not through the backend's uvicorn worker (which is single-threaded for I/O)
2. **Resumable uploads**: COS supports multipart upload; the frontend can split large files
3. **Reduced ECS bandwidth**: File data flows from client to COS; the backend only downloads after the upload completes
4. **CDN acceleration**: COS integrates with Tencent Cloud CDN for faster downloads if needed later

## Required Changes

### 1. Frontend -- Replace direct upload with COS flow

**File**: `web/src/...` (login/upload page)

Current flow:
```typescript
const formData = new FormData();
formData.append("file", file);
formData.append("title", title);
await fetch("/api/books/upload", { method: "POST", body: formData });
```

New flow:
```typescript
// Step 1: Get pre-signed URL
const presignRes = await fetch("/api/books/presign", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ filename: file.name, file_type: file.name.split('.').pop() }),
});
const { upload_url, key } = await presignRes.json();

// Step 2: Upload directly to COS
await fetch(upload_url, { method: "PUT", body: file });

// Step 3: Notify backend to import
const importRes = await fetch("/api/books/import-cos", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ key, filename: file.name, title, author }),
});
```

### 2. Backend -- Confirm `presign` endpoint handles auth

**File**: `app/routers/books.py`, route `POST /api/books/presign` (line 141)

- Already requires JWT auth via `user = Depends(get_current_user)`
- Already calls `get_presigned_upload(user_id=..., filename=..., file_type=...)`
- No changes needed -- endpoint is ready

### 3. Backend -- Confirm `import-cos` endpoint handles auth

**File**: `app/routers/books.py`, route `POST /api/books/import-cos` (line 159)

- Already requires JWT auth
- Already downloads from COS, saves locally, creates DB record, triggers background parse
- Already deletes COS temp object after successful download
- No changes needed -- endpoint is ready

### 4. Environment variables

Ensure the ECS `.env` file has COS credentials:

```bash
COS_REGION=ap-guangzhou
COS_SECRET_ID=<tencent-cloud-secret-id>
COS_SECRET_KEY=<tencent-cloud-secret-key>
COS_BUCKET=xiugua-uploads-<appid>
```

### 5. CORS configuration for COS

COS bucket must allow PUT requests from the frontend domain. Configure in Tencent Cloud COS console:

- **AllowedOrigin**: `https://www.xiugua-reading.cn`, `http://localhost:3000`
- **AllowedMethod**: `PUT`, `HEAD`
- **AllowedHeader**: `*`
- **ExposeHeader**: `ETag`
- **MaxAgeSeconds**: `3600`

### 6. (Optional) Remove direct `/api/books/upload` in the future

Once the COS flow is verified in production, the old `POST /api/books/upload` endpoint can be deprecated or removed to reduce maintenance surface.

## Rollback Plan

If the COS flow has issues:

1. Revert the frontend to use `POST /api/books/upload` directly
2. The server-side upload endpoint remains in the code and is unaffected
3. No data migration needed -- book files are always eventually stored on local disk regardless of upload path

## Testing Checklist

- [ ] `POST /api/books/presign` returns a valid pre-signed URL
- [ ] Pre-signed URL accepts a PUT request with a file
- [ ] `POST /api/books/import-cos` downloads the file from COS
- [ ] COS temp object is deleted after download
- [ ] Book record is created with correct metadata
- [ ] Background parsing triggers successfully
- [ ] Frontend upload flow works end-to-end (local dev + production)
- [ ] CORS errors do not appear in browser console during PUT to COS
