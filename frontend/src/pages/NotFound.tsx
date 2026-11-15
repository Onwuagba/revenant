import { Link } from "react-router-dom";
export default function NotFound() {
  return <div className="state"><h2>Nothing is buried here</h2><p>That page does not exist.</p><Link to="/">Return home</Link></div>;
}
