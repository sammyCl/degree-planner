import { Component, type ReactNode } from 'react'
import { ProblemScreen } from './building/ProblemScreen.tsx'

interface Props {
  /** leave the broken screen */
  onReset: () => void
  children: ReactNode
}

/** If a screen throws while drawing, say so and offer a way back, instead of leaving a blank page. */
export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  reset = () => {
    this.props.onReset()
    this.setState({ failed: false })
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <ProblemScreen
        title="This page ran into a problem"
        message="Something on this screen could not be shown. Go back to setup and build the plan again."
        onBack={this.reset}
      />
    )
  }
}
