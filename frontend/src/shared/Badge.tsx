export default function Badge({ value }: { value?: string }) {
  return (
    <span
      className={"badge " + (value || "").toLowerCase().replaceAll("_", "-")}
    >
      {(value || "UNKNOWN").replaceAll("_", " ")}
    </span>
  );
}
