type FoundationStateProps = {
  index: string;
  title: string;
  description: string;
};

export function FoundationState({
  index,
  title,
  description,
}: FoundationStateProps) {
  return (
    <section className="foundation-state" aria-labelledby="foundation-title">
      <div className="foundation-state__index" aria-hidden="true">
        {index}
      </div>
      <div>
        <p className="foundation-state__label">Current state</p>
        <h2 id="foundation-title">{title}</h2>
        <p>{description}</p>
      </div>
    </section>
  );
}
