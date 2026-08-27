import { Client } from "pg";

export interface AuditState {
  exists: boolean;
  totalWrites: number;
}

export async function readAuditState(
  databaseUrl: string,
  idempotencyKey: string,
): Promise<AuditState> {
  const client = new Client({ connectionString: databaseUrl });
  await client.connect();
  try {
    const result = await client.query<{
      exists: boolean;
      total_writes: string;
    }>(
      `
      SELECT
        EXISTS(
          SELECT 1 FROM sponsor_compatibility_audit
          WHERE idempotency_key = $1
        ) AS exists,
        COUNT(*)::text AS total_writes
      FROM sponsor_compatibility_audit
      `,
      [idempotencyKey],
    );
    const row = result.rows[0];
    if (!row) {
      throw new Error("PostgreSQL returned no compatibility audit row");
    }
    return { exists: row.exists, totalWrites: Number(row.total_writes) };
  } finally {
    await client.end();
  }
}
