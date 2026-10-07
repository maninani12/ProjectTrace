export type InfrastructureSettings = {
  environment: string;
  require_network_policy: boolean;
  require_healthcheck: boolean;
  require_logging: boolean;
  require_resource_requests: boolean;
  allowed_image_registries: string[];
  rules: Record<
    string,
    { enabled?: boolean; severity?: string; environments?: string[] }
  >;
};

export const defaultInfrastructure: InfrastructureSettings = {
  environment: "UNKNOWN",
  require_network_policy: false,
  require_healthcheck: false,
  require_logging: false,
  require_resource_requests: false,
  allowed_image_registries: [],
  rules: {},
};

export default function InfrastructurePolicy({
  value,
  onChange,
  disabled,
  selectedRule,
}: {
  value: InfrastructureSettings;
  onChange: (value: InfrastructureSettings) => void;
  disabled: boolean;
  selectedRule: string;
}) {
  return (
    <fieldset disabled={disabled} className="quality-form">
      <legend>Infrastructure policy</legend>
      <p>
        Static declaration checks. Select the environment explicitly; filenames
        never establish deployment state.
      </p>
      <label>
        Environment
        <select
          value={value.environment}
          onChange={(e) => onChange({ ...value, environment: e.target.value })}
        >
          {["UNKNOWN", "DEVELOPMENT", "TEST", "STAGING", "PRODUCTION"].map(
            (e) => (
              <option key={e}>{e}</option>
            ),
          )}
        </select>
      </label>
      {(
        [
          [
            "require_network_policy",
            "Require namespace NetworkPolicy declarations",
          ],
          ["require_healthcheck", "Require final Dockerfile healthcheck"],
          [
            "require_logging",
            "Require logging configuration in modeled resources",
          ],
          ["require_resource_requests", "Require Kubernetes resource requests"],
        ] as const
      ).map(([key, label]) => (
        <label key={key}>
          <input
            type="checkbox"
            checked={value[key]}
            onChange={(e) => onChange({ ...value, [key]: e.target.checked })}
          />
          {label}
        </label>
      ))}
      <label>
        Approved image registries (comma separated)
        <input
          value={value.allowed_image_registries.join(", ")}
          maxLength={2000}
          onChange={(e) =>
            onChange({
              ...value,
              allowed_image_registries: e.target.value
                .split(",")
                .map((x) => x.trim())
                .filter(Boolean),
            })
          }
        />
      </label>
      {selectedRule.startsWith("PT-IAC-") && (
        <label>
          Apply {selectedRule} in environment
          <select
            value={value.rules[selectedRule]?.environments?.[0] || "ALL"}
            onChange={(e) =>
              onChange({
                ...value,
                rules: {
                  ...value.rules,
                  [selectedRule]: {
                    ...value.rules[selectedRule],
                    environments:
                      e.target.value === "ALL" ? [] : [e.target.value],
                  },
                },
              })
            }
          >
            <option value="ALL">All environments</option>
            {["UNKNOWN", "DEVELOPMENT", "TEST", "STAGING", "PRODUCTION"].map(
              (e) => (
                <option key={e}>{e}</option>
              ),
            )}
          </select>
        </label>
      )}
      <p>
        NetworkPolicy presence does not prove selector coverage. Image policy
        does not establish CVE status. Changes apply to future analyses.
      </p>
    </fieldset>
  );
}
