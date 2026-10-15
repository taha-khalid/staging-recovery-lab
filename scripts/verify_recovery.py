import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=".env.test")
    parser.add_argument("--project", default="recovery-tests")
    args = parser.parse_args()
    
    compose = [
        "docker", "compose",
        "--env-file", args.env_file,
        "-p", args.project,
    ]
    
    def run(*command, input_data=None):
        result = subprocess.run(
            [*compose, *command],
            cwd=ROOT,
            input=input_data,
            capture_output=True,
        )
        
        if result.returncode:
            raise RuntimeError(
                result.stderr.decode(errors="replace")
            )
        
        return result.stdout

    def postgres(tool, *arguments, input_data=None):
        # Read the username inside the container.
        # No password is placed in the command line.
        return run(
            "exec", "-T", "db",
            "sh", "-c",
            'exec "$@" -U "$POSTGRES_USER"',
            "sh", tool, *arguments,
            input_data=input_data,
        )
    
    def sql(database, statement):
        return postgres(
            "psql",
            "-X",
            "-v", "ON_ERROR_STOP=1",
            "-A", "-t",
            "-d", database,
            "-c", statement,
        ).decode().strip()
        
    source = run(
        "exec", "-T", "db",
        "printenv", "POSTGRES_DB",
    ).decode().strip()
    
    # This verifications inserts sample data
    # Refule to run against the development database
    if source != "appdb_test":
        raise RuntimeError(
            f"Expected appdb_test, found {source!r}. "
            "Use the isolated test environment."
        )
    
    token = uuid.uuid4().hex
    recovery =  f"recovery_{token}"
    marker = f"recovery-check-{token}"
    recovery_created = False
    
    output = ROOT / "backups"
    output.mkdir(exist_ok=True)
    backup_path =  output / f"{token}.dump"
    
    snapshot_sql = """
        SELECT COALESCE(
            json_agg(record ORDER BY record.id),
            '[]'::json
        )
        FROM (
            SELECT id, name, created_at
            FROM public.items
        ) AS record;
    """
    
    try:
        # marker contains only a fixed prefix and generated hex characters.
        sql(
            source, 
            f"INSERT INTO public.items (name) VALUES ('{marker}')",
        )
        
        expected = json.loads(sql(source, snapshot_sql))
        assert any(row["name"] == marker for row in expected)
        
        started = time.monotonic()
        
        archive = postgres(
            "pg_dump",
            "-d", source,
            "--format=custom",
        )
        backup_path.write_bytes(archive)
        
        backup_seconds =  time.monotonic() - started
        
        postgres(
            "createdb",
            "--template=template0",
            recovery,
        )
        recovery_created = True
        
        started = time.monotonic()
        
        postgres(
            "pg_restore",
            "-d", recovery,
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            "--single-transaction",
            input_data=backup_path.read_bytes(),
        )
        
        restore_seconds= time.monotonic() - started
        restored =  json.loads(sql(recovery, snapshot_sql))
        
        if restored != expected:
            raise AssertionError(
                "Restored items do not match the source snapshot"
            )
        
        report = {
            "status": "passed",
            "source_database": source,
            "restored_item_count": len(restored),
            "backup_bytes": backup_path.stat().st_size,
            "backup_sha256": hashlib.sha256(archive).hexdigest(),
            "backup_seconds": round(backup_seconds, 3),
            "restore_seconds": round(restore_seconds, 3),
        }
        
        report_path =  ROOT / "reports" / "recovery.json"
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
        
        print(json.dumps(report, indent=2))
    
    finally:
        try:
            if recovery_created:
                postgres("dropdb", recovery)
        
        finally:
            sql(
                source,
                f"DELETE FROM public.items WHERE name = '{marker}'"
            )

if __name__ == "__main__":
    main()