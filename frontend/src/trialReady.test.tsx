// Getting ready for the user trial: bad answers, bad timing and keyboard use must not lose work or blank the page.
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { StrictMode, useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { checkPlan, readTranscript, submitSetup } from './api.ts'
import App from './App.tsx'
import { PlannerPage } from './planner/PlannerPage.tsx'
import { samplePlan } from './samplePlan.ts'
import { SetupPage } from './setup/SetupPage.tsx'
import type { UploadedFile } from './setup/transcript.ts'
import { TranscriptUpload } from './setup/TranscriptUpload.tsx'
import type { AgentRequest, CompletedCourse, Plan, TranscriptReading } from './types.ts'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body })
const fail = (status: number, body: unknown) => ({ ok: false, status, json: async () => body })
const notJson = (status: number) => ({
  ok: status < 300,
  status,
  json: async () => {
    throw new SyntaxError('Unexpected end of JSON input')
  },
})
const usage = { input_tokens: 1, output_tokens: 1, steps: 1 }
const good = { status: 'ok', plan: samplePlan, explanation: '', problems: [], usage }
const request: AgentRequest = {
  student: samplePlan.student,
  semesters: 8,
  start_term: 'Fall 2026',
  include_summers: false,
  overrides: [],
}

function stubSubmit(answer: () => unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/health')) return ok({ status: 'ok', database: 'ok' })
      if (url.endsWith('/plans/check')) return ok(JSON.parse(init?.body as string))
      return answer()
    }),
  )
}

function build() {
  fireEvent.click(screen.getByRole('combobox', { name: 'Program' }))
  fireEvent.mouseDown(screen.getByRole('option', { name: /^Bachelor of Science in Computer Science/ }))
  fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
}

describe('answers the page cannot read', () => {
  it.each([
    ['an empty object', {}],
    ['a plan with no semesters', { ...good, plan: { ...samplePlan, semesters: undefined } }],
    ['a semester with no course list', { ...good, plan: { ...samplePlan, semesters: [{ semester_id: 's', label: 'Fall 2026' }] } }],
    ['a plan with no summary', { ...good, plan: { ...samplePlan, summary: undefined } }],
    ['null', null],
  ])('says so, with a retry, for %s', async (_name, body) => {
    stubSubmit(() => ok(body))
    render(<App />)
    build()
    expect(await screen.findByRole('heading', { name: 'Something went wrong' })).toBeInTheDocument()
    expect(screen.getByText(/could not read/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('says so when a 200 answer is not JSON', async () => {
    stubSubmit(() => notJson(200))
    await expect(submitSetup(request)).rejects.toMatchObject({ name: 'ApiError', kind: 'server' })
  })

  it('tidies lists and text of the wrong type instead of passing them to the page', async () => {
    stubSubmit(() => ok({ ...good, explanation: null, choices: 'one', checks: [null, 'ask'], problems: undefined }))
    await expect(submitSetup(request)).resolves.toMatchObject({ explanation: '', choices: [], checks: ['ask'], problems: [] })
  })

  it('rejects a check answer that is not a plan, so the change is undone instead of crashing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ok({ detail: 'odd' })))
    await expect(checkPlan(samplePlan)).rejects.toMatchObject({ name: 'ApiError', kind: 'server' })
  })

  it.each([
    [502, 'which the dev server sends when the backend is off'],
    [504, 'a gateway timeout'],
  ])('reads %i without a body as the backend being unreachable (%s)', async (status) => {
    stubSubmit(() => notJson(status))
    render(<App />)
    build()
    expect(await screen.findByRole('heading', { name: "Can't reach the server" })).toBeInTheDocument()
  })

  it('still shows the backend\'s own words for its 500', async () => {
    stubSubmit(() => fail(500, { detail: 'Something went wrong on our end.' }))
    await expect(submitSetup(request)).rejects.toMatchObject({ kind: 'server', message: 'Something went wrong on our end.' })
  })
})

describe('a page that fails to draw', () => {
  it('keeps the header, says what happened, and goes back to setup with the choices kept', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const broken: Plan = {
      ...samplePlan,
      flags: [{ flag_id: 'x', type: 'unlisted_course', severity: 'warning', course_id: null, message: {}, overridable: false, overridden: false } as never],
    }
    stubSubmit(() => ok({ ...good, plan: broken }))
    render(<App />)
    build()
    expect(await screen.findByRole('heading', { name: 'This page ran into a problem' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Degree Planner' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Back to setup' }))
    expect(screen.getByRole('combobox', { name: 'Program' })).toHaveValue('Bachelor of Science in Computer Science')
  })
})

describe('the backend status', () => {
  it('is checked again when the screen changes, not only when the page opens', async () => {
    let up = false
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith('/health')) {
          if (!up) throw new TypeError('Failed to fetch')
          return ok({ status: 'ok', database: 'ok' })
        }
        if (url.endsWith('/plans/check')) return ok(JSON.parse(init?.body as string))
        return ok(good)
      }),
    )
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('backend-status')).toHaveTextContent('not running'))
    up = true
    build()
    await waitFor(() => expect(screen.getByTestId('backend-status')).toHaveTextContent('connected'))
  })
})

describe('a file dropped beside the upload box', () => {
  it('does not make the browser open it and throw the page away', () => {
    stubSubmit(() => ok(good))
    render(<App />)
    const dataTransfer = { types: ['Files'], files: [], dropEffect: '' }
    expect(fireEvent.dragOver(document.body, { dataTransfer })).toBe(false) // false: the default was prevented
    expect(fireEvent.drop(document.body, { dataTransfer })).toBe(false)
  })

  it('leaves other drags, such as selected text, alone', () => {
    stubSubmit(() => ok(good))
    render(<App />)
    expect(fireEvent.drop(document.body, { dataTransfer: { types: ['text/plain'] } })).toBe(true)
  })
})

describe('requests that never answer', () => {
  const hang = () =>
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))),
      ),
    )

  it('gives up on a plan check after 30 seconds', async () => {
    vi.useFakeTimers()
    hang()
    const result = expect(checkPlan(samplePlan)).rejects.toMatchObject({ kind: 'server', message: expect.stringMatching(/too long/) })
    await vi.advanceTimersByTimeAsync(30_000)
    await result
  })

  it('gives up on reading a transcript after five minutes', async () => {
    vi.useFakeTimers()
    hang()
    const result = expect(readTranscript(new File(['x'], 't.pdf'), null)).rejects.toMatchObject({
      kind: 'server',
      message: expect.stringMatching(/too long/),
    })
    await vi.advanceTimersByTimeAsync(300_000)
    await result
  })

  it('still reports a cancel by the caller as cancelled', async () => {
    hang()
    const abort = new AbortController()
    const result = checkPlan(samplePlan, abort.signal)
    abort.abort()
    await expect(result).rejects.toMatchObject({ kind: 'aborted' })
  })
})

// ---------- transcript upload ----------

const course = (code: string): CompletedCourse => ({ code, credits: 4, term: 'transfer', transfer_from: null })
const reading = (courses: CompletedCourse[], extra: Partial<TranscriptReading> = {}): TranscriptReading => ({
  school: 'Colorado School of Mines',
  from_mines: true,
  system: null,
  courses,
  unmatched: [],
  skipped: [],
  tes_url: 'https://example.test/tes',
  known_schools: [],
  ...extra,
})

function uploadHost() {
  const latest = { current: [] as CompletedCourse[] }
  function Host() {
    const [courses, setCourses] = useState<CompletedCourse[]>([])
    const [files, setFiles] = useState<UploadedFile[]>([])
    latest.current = courses
    return (
      <TranscriptUpload
        courses={courses}
        files={files}
        onChange={(c, f) => {
          setCourses(c)
          setFiles(f)
        }}
        thisYear={2026}
      />
    )
  }
  render(<Host />)
  return latest
}

const csv = (name: string) => new File(['x'], name, { type: 'text/csv' })
const pick = (name: string) => fireEvent.change(screen.getByLabelText('Transcript file'), { target: { files: [csv(name)] } })
const drop = (...files: File[]) =>
  fireEvent.drop(screen.getByText('or drop a .csv or .pdf here'), { dataTransfer: { files, types: ['Files'] } })

function addByHand(code: string) {
  fireEvent.click(screen.getByRole('button', { name: '+ Add a course by hand' }))
  fireEvent.change(screen.getByLabelText('Course code'), { target: { value: code } })
  fireEvent.change(screen.getByLabelText('Credits'), { target: { value: '3' } })
  fireEvent.click(screen.getByRole('combobox', { name: 'When you took it' }))
  fireEvent.mouseDown(screen.getByRole('option', { name: 'AP credit' }))
}

describe('transcript upload timing', () => {
  it('keeps a course typed in while a file was still being read', async () => {
    let finish: (r: unknown) => void = () => {}
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => (finish = resolve))))
    const latest = uploadHost()
    pick('a.csv')
    addByHand('MATH111')
    fireEvent.click(screen.getByRole('button', { name: 'Add course' }))
    await act(async () => finish(ok(reading([course('PHGN100')]))))
    expect(latest.current.map((c) => c.code)).toEqual(['MATH111', 'PHGN100'])
  })

  it('does not start a second read over the first, and says to wait', async () => {
    const fetchMock = vi.fn(() => new Promise(() => {}))
    vi.stubGlobal('fetch', fetchMock)
    uploadHost()
    pick('a.csv')
    drop(csv('b.csv'))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('alert')).toHaveTextContent('Still reading a.csv')
  })

  it('says that only one of several dropped files is read', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ok(reading([course('PHGN100')]))))
    uploadHost()
    drop(csv('a.csv'), csv('b.csv'))
    expect(await screen.findByText(/One file at a time/)).toHaveTextContent('b.csv')
  })

  it('holds the plan back while a transcript is being read, so its courses are not left out', async () => {
    let finish: (r: unknown) => void = () => {}
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => (finish = resolve))))
    const onSubmit = vi.fn()
    render(<SetupPage onSubmit={onSubmit} today={new Date(2026, 0, 1)} />)
    fireEvent.click(screen.getByRole('checkbox', { name: /already completed/ }))
    pick('a.csv')
    build()
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText(/Wait for your transcript/)).toBeInTheDocument()

    await act(async () => finish(ok(reading([course('PHGN100')]))))
    expect(screen.queryByText(/Wait for your transcript/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit.mock.calls[0][0].student.completed_courses).toHaveLength(1)
  })

  it('stops holding the plan back when the completed-courses box is unticked mid-read', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    const onSubmit = vi.fn()
    render(<SetupPage onSubmit={onSubmit} today={new Date(2026, 0, 1)} />)
    const box = screen.getByRole('checkbox', { name: /already completed/ })
    fireEvent.click(box)
    pick('a.csv')
    fireEvent.click(box)
    build()
    expect(onSubmit).toHaveBeenCalled()
  })

  it('says why a transfer course was not added when its Mines course is already listed', async () => {
    const unmatched = ['MAT 1', 'MAT 2'].map((code) => ({
      code,
      title: 'Calculus',
      credits: 4,
      term: 'transfer',
      in_progress: false,
      suggestion: 'MATH111',
      reason: '',
    }))
    vi.stubGlobal('fetch', vi.fn(async () => ok(reading([], { unmatched, school: 'X College', from_mines: false }))))
    const latest = uploadHost()
    pick('a.csv')
    await screen.findByRole('combobox', { name: 'Mines course for MAT 1' })
    fireEvent.click(screen.getAllByRole('button', { name: 'Add' })[0])
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(latest.current).toHaveLength(1)
    expect(screen.getByRole('combobox', { name: 'Mines course for MAT 2' })).toBeInTheDocument() // still there to change
    expect(screen.getByRole('alert')).toHaveTextContent('MATH111 is already in the list')
  })
})

describe('the Enter key in the completed-courses fields', () => {
  it('adds the course instead of submitting the setup form', () => {
    const latest = uploadHost()
    addByHand('MATH111')
    for (const name of ['Course code', 'Credits']) {
      expect(fireEvent.keyDown(screen.getByLabelText(name), { key: 'Enter' })).toBe(false)
    }
    expect(latest.current.map((c) => c.code)).toEqual(['MATH111'])
  })

  it('adds the transfer course whose box has the cursor', async () => {
    const unmatched = [{ code: 'MAT 1', title: 'Calculus', credits: 4, term: 'transfer', in_progress: false, suggestion: 'MATH111', reason: '' }]
    vi.stubGlobal('fetch', vi.fn(async () => ok(reading([], { unmatched, school: 'X College', from_mines: false }))))
    const latest = uploadHost()
    pick('a.csv')
    const field = await screen.findByRole('combobox', { name: 'Mines course for MAT 1' })
    expect(fireEvent.keyDown(field, { key: 'Enter' })).toBe(false)
    expect(latest.current.map((c) => c.code)).toEqual(['MATH111'])
  })
})

// ---------- planner ----------

const card = (code: string) => screen.getByRole('button', { name: new RegExp(`^${code} `) })
const column = (label: string) => screen.getByRole('region', { name: label })
function drag(code: string, to: string) {
  const dataTransfer = { setData: vi.fn(), effectAllowed: '' }
  fireEvent.dragStart(card(code), { dataTransfer })
  fireEvent.dragOver(column(to), { dataTransfer })
  fireEvent.drop(column(to), { dataTransfer })
}

describe('planner edits and the keyboard', () => {
  it('leaves no undo history behind when two quick changes both fail', async () => {
    const rejects: (() => void)[] = []
    vi.stubGlobal('fetch', vi.fn(() => new Promise((_r, reject) => rejects.push(() => reject(new TypeError('down'))))))
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    drag('CSM101', 'Spring 2027')
    drag('CSM101', 'Fall 2027')
    await act(async () => rejects.forEach((r) => r()))
    expect(within(column('Fall 2026')).getByRole('button', { name: /^CSM101 / })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Undo/ })).not.toBeInTheDocument()
  })

  const echo = () => vi.stubGlobal('fetch', vi.fn(async (_u: string, init: RequestInit) => ok(JSON.parse(init.body as string))))

  it.each(['Escape', 'Close'])('gives focus back to the card when its details are closed with %s', (how) => {
    echo()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    card('CSM101').focus()
    fireEvent.keyDown(card('CSM101'), { key: 'Enter' })
    if (how === 'Escape') fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    else fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(card('CSM101')).toHaveFocus()
  })

  it('keeps focus on the course after moving it from its details', async () => {
    echo()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    fireEvent.click(card('CSM101'))
    fireEvent.click(screen.getByRole('combobox', { name: 'Move to semester' }))
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Spring 2027' }))
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Move' })))
    expect(card('CSM101')).toHaveFocus()
  })

  it('closes only the semester list on Escape, not the whole details box', () => {
    echo()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    fireEvent.click(card('CSM101'))
    const list = screen.getByRole('combobox', { name: 'Move to semester' })
    fireEvent.click(list)
    fireEvent.keyDown(list, { key: 'Escape' })
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.keyDown(list, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('keeps the loading placeholder while the completed courses are checked, in strict mode too', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_r, reject) => init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))),
      ),
    )
    const plan = { ...samplePlan, student: { ...samplePlan.student, completed_courses: [course('MATH111')] } }
    await act(async () => {
      render(
        <StrictMode>
          <PlannerPage plan={plan} onBack={vi.fn()} />
        </StrictMode>,
      )
    })
    expect(screen.getByLabelText('Loading which requirements they meet')).toBeInTheDocument()
  })
})
