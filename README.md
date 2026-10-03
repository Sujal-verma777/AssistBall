# AssistBall

AssistBall is a Windows desktop AI assistant that captures the current screen, generates two proactive suggestions, and answers screen-aware questions with optional streaming responses.

## Architecture

```text
Electron floating ball
        |
        +--> screenshot capture
        |
        +--> local FastAPI backend
                 |
                 +--> /suggest       -> 2 proactive suggestions
                 +--> /ask           -> normal answer
                 +--> /ask/stream    -> streaming answer
                 |
                 +--> Claude / OpenAI / Gemini / Mock
```

The Electron main process owns the backend API key. The renderer only communicates with Electron through a context-isolated preload bridge.

## Run locally

### Recommended Windows setup

Run PowerShell once:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1
```

This creates `backend/venv`, installs Python dependencies, and installs Node dependencies.

### Manual setup

```powershell
npm install
python -m pip install -r backend/requirements.txt
```

### 3. Configure AI provider

For an offline UI/API test, the included `backend/.env` uses `PROVIDER=mock`.

For real AI, edit `backend/.env` and set one provider:

```text
PROVIDER=gemini
GEMINI_API_KEY=your-key
```

or Claude/OpenAI as supported by the backend.

**Never commit `backend/.env`.** Use `backend/.env.example` as the GitHub-safe template.

### 4. Start the complete app

```powershell
npm run dev
```

Electron automatically starts the FastAPI backend, waits for `/health`, and then opens the floating AssistBall.

### 5. Backend tests

```powershell
npm run backend:test
```

## Production build

The production build uses PyInstaller to bundle the FastAPI backend, then electron-builder creates the Windows installer.

```powershell
npm run build:app
```

The generated installer is placed in `dist/`.

## Important

The generated Windows installer still needs a real AI provider key/configuration strategy before distribution to end users. Do not ship a personal provider API key inside a public installer. For a public product, put provider credentials behind your own authenticated cloud service or use per-user authentication.
