import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

  it('goes from the setup form to the planner and back', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', database: 'ok' }) }))
    render(<App />)
    fireEvent.click(screen.getByRole('combobox', { name: 'Program' }))
    fireEvent.mouseDown(screen.getByRole('option', { name: /Computer Science \(General Track\)/ }))
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(screen.getByRole('region', { name: 'Fall 2026' })).toBeInTheDocument()
    expect(screen.getByText(/This is a sample plan/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edit setup' }))
    expect(screen.getByRole('form', { name: 'Plan setup' })).toBeInTheDocument()
  })
})
