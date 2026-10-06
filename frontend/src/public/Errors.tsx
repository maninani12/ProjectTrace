import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Link } from "react-router";
export function NotFound() {
  return (
    <div className="public-document">
      <span className="eyebrow">404 / PAGE NOT FOUND</span>
      <h1>This path has no page.</h1>
      <p>The product and Guide are a good place to continue.</p>
      <div className="public-ctas">
        <Link className="primary" to="/">
          Return Home
        </Link>
        <Link to="/app">Open ProjectTrace</Link>
        <Link to="/guide">ProjectTrace Guide</Link>
      </div>
    </div>
  );
}
export class AppBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    /* Never log source context or credentials. */
  }
  render() {
    return this.state.failed ? (
      <main className="public-document">
        <span className="eyebrow">PROJECTTRACE / DISPLAY ERROR</span>
        <h1>We couldn’t display this view.</h1>
        <p>
          Your source remains in its workspace. Reload the view or return to the
          Guide.
        </p>
        <div className="public-ctas">
          <button className="primary" onClick={() => window.location.reload()}>
            Reload view
          </button>
          <a href="/">Return Home</a>
          <a href="/guide">ProjectTrace Guide</a>
        </div>
      </main>
    ) : (
      this.props.children
    );
  }
}
