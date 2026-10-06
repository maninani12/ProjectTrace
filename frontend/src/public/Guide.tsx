import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { glossary, guideTopics, mapStages } from "./guideContent";
import { statuses } from "./content";
import Badge from "../shared/Badge";

export function ProductMap() {
  return (
    <nav className="product-map" aria-label="Interactive product map">
      {mapStages.map(([name, id], i) => (
        <div key={id}>
          <Link to={`/guide/${id}`}>
            <span className="map-number">{String(i + 1).padStart(2, "0")}</span>
            {name}
          </Link>
          {i < mapStages.length - 1 && (
            <span className="map-arrow" aria-hidden="true">
              ↓
            </span>
          )}
        </div>
      ))}
    </nav>
  );
}
export default function Guide() {
  const { topic: topicId = "start" } = useParams();
  const [search, setSearch] = useState("");
  const [params, setParams] = useSearchParams();
  const mode = params.get("mode") === "technical" ? "technical" : "simple";
  const topic = guideTopics.find((item) => item.id === topicId);
  if (!topic)
    return (
      <div className="public-document">
        <h1>Guide topic not found</h1>
        <p>Choose a topic from the ProjectTrace Guide.</p>
        <Link className="primary" to="/guide">
          Open the Guide
        </Link>
      </div>
    );
  const index = guideTopics.indexOf(topic);
  const aliases: Record<string, string> = {
    dependencies: "dependency packages sbom licenses sca",
    "application-security": "sast taint data flow",
    "code-quality": "complexity duplication metrics",
    infrastructure: "iac terraform kubernetes docker",
    ask: "question answer search",
    "security-privacy": "source retention deletion data",
  };
  const filtered = guideTopics.filter((item) =>
    `${item.title} ${item.simple} ${aliases[item.id] || ""}`
      .toLowerCase()
      .includes(search.trim().toLowerCase()),
  );
  return (
    <div className="guide-layout">
      <aside className="guide-navigation">
        <Link className="eyebrow" to="/guide">
          PROJECTTRACE GUIDE
        </Link>
        <p>One product. One connected investigation.</p>
        <label>
          Find a topic
          <input
            aria-label="Find a guide topic"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <nav aria-label="Guide topics">
          {filtered.map((item, i) => (
            <Link
              key={item.id}
              to={`/guide/${item.id}`}
              aria-current={topic.id === item.id ? "page" : undefined}
            >
              <span aria-hidden="true">
                {String(guideTopics.indexOf(item) + 1).padStart(2, "0")}
              </span>
              {item.title}
            </Link>
          ))}
          {!filtered.length && (
            <p role="status">No matching topics. Try “claims” or “source”.</p>
          )}
        </nav>
      </aside>
      <article className="guide-article">
        <div className="guide-kicker">
          <span className="eyebrow">
            LEARN / {String(index + 1).padStart(2, "0")}
          </span>
          <Link to="/app">Open ProjectTrace ↗</Link>
        </div>
        <h1>{topic.title}</h1>
        <p className="guide-intro">{topic.simple}</p>
        <div
          className="explanation-mode"
          role="group"
          aria-label="Explanation mode"
        >
          <button
            aria-pressed={mode === "simple"}
            onClick={() => setParams({ mode: "simple" }, { replace: true })}
          >
            Simple explanation
          </button>
          <button
            aria-pressed={mode === "technical"}
            onClick={() => setParams({ mode: "technical" }, { replace: true })}
          >
            Technical details
          </button>
        </div>
        {mode === "technical" && (
          <section className="guide-technical">
            <h2>Technical details</h2>
            <p>{topic.technical}</p>
          </section>
        )}
        <section>
          <h2>Why does it matter?</h2>
          <p>{topic.why}</p>
        </section>
        <div className="guide-io">
          <section>
            <h2>What does ProjectTrace analyze?</h2>
            <p>{topic.inputs}</p>
          </section>
          <section>
            <h2>What does it produce?</h2>
            <p>{topic.outputs}</p>
          </section>
        </div>
        <section className="guide-example">
          <span className="eyebrow">EXAMPLE</span>
          <p>{topic.example}</p>
        </section>
        {topic.id === "product-map" && <ProductMap />}
        {topic.id === "statuses" && (
          <dl className="guide-statuses">
            {statuses.map(([value, description]) => (
              <div key={value}>
                <dt>
                  <Badge value={value} />
                </dt>
                <dd>{description}</dd>
              </div>
            ))}
          </dl>
        )}
        {topic.id === "glossary" && (
          <dl className="glossary">
            {Object.entries(glossary).map(([term, definition]) => (
              <div key={term}>
                <dt>{term}</dt>
                <dd>{definition}</dd>
              </div>
            ))}
          </dl>
        )}
        <section>
          <h2>How is it connected?</h2>
          <div className="guide-related">
            {topic.connections.map((id) => (
              <Link key={id} to={`/guide/${id}`}>
                {guideTopics.find((item) => item.id === id)?.title}{" "}
                <span aria-hidden="true">→</span>
              </Link>
            ))}
          </div>
        </section>
        <section>
          <h2>What should I do?</h2>
          <p>{topic.action}</p>
        </section>
        <section className="guide-limits">
          <h2>Limits to keep in view</h2>
          <p>{topic.limitations}</p>
        </section>
        <nav className="guide-next" aria-label="Adjacent guide topics">
          {index > 0 && (
            <Link to={`/guide/${guideTopics[index - 1].id}`}>
              ← {guideTopics[index - 1].title}
            </Link>
          )}
          {index < guideTopics.length - 1 && (
            <Link to={`/guide/${guideTopics[index + 1].id}`}>
              {guideTopics[index + 1].title} →
            </Link>
          )}
        </nav>
      </article>
    </div>
  );
}
