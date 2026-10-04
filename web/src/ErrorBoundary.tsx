import { Component, type ReactNode } from "react";
import { ErrorFallback } from "./ErrorFallback";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  override render() {
    return this.state.hasError ? <ErrorFallback /> : this.props.children;
  }
}
