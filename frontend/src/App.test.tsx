import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('shows the title and reports the backend as connected', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', database: 'ok' }) }),
    )
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Degree Planner' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('backend-status')).toHaveTextContent('connected'))
  })

  it('does not crash when the backend is down', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')))
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('backend-status')).toHaveTextContent('not running'))
  })
})
