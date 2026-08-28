type ServiceStateProps = {
  title: string;
  detail: string;
  tone?: "neutral" | "error";
};

export function ServiceState({
  title,
  detail,
  tone = "neutral",
}: ServiceStateProps) {
  return (
    <div
      className={`service-state service-state--${tone}`}
      role={tone === "error" ? "alert" : "status"}
    >
      <span aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
    </div>
  );
}
