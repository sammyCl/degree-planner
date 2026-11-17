// All backend calls go through /api. In development Vite proxies /api to the FastAPI server
// (see vite.config.ts), so the browser never needs the backend's address or CORS settings.

export async function getHealth(): Promise<{ status: string; database: string }> {
  const response = await fetch('/api/health')
  if (!response.ok) {
    throw new Error(`Backend returned ${response.status}`)
  }
  return response.json()
}
