import Link from "next/link";

export default function NotFound() {
  return (
    <div className="not-found">
      <h1>Page not found</h1>
      <p>
        That page does not exist. The workspace covers prospects, discovery, campaigns,
        workflow runs and analytics.
      </p>
      <Link className="primary-button" href="/prospects">
        Open prospects
      </Link>
    </div>
  );
}
