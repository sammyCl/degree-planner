import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Vitest has no globals here, so Testing Library cannot clean up between tests on its own.
afterEach(cleanup)
// the app keeps the plan in sessionStorage across reloads; each test starts fresh
afterEach(() => sessionStorage.clear())
