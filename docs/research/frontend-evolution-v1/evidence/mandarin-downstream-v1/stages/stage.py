import datetime, hashlib, json, os, pathlib, signal, subprocess, sys, time
stage, cwd, commands_json = sys.argv[1:]
root = pathlib.Path(__file__).parent
commands = json.loads(commands_json)
receipt_path, log_path = root / (stage + '.json'), root / (stage + '.log')
if receipt_path.exists() or log_path.exists():
    raise SystemExit('fresh stage required')
started = time.monotonic()
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
receipt = {'stage': stage, 'started_at': utc(), 'budget_seconds': 300.0, 'cwd': cwd,
           'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=cwd, text=True).strip(),
           'commands': [], 'timing_scope': 'before first command through all child exits; includes runner evidence sealing'}
exit_code = 0
with log_path.open('wb') as log:
    try:
        for command in commands:
            remaining = 300.0 - (time.monotonic() - started)
            if remaining <= 0: raise TimeoutError('stage budget exhausted')
            entry = {'argv': command, 'started_at': utc()}
            receipt['commands'].append(entry)
            process = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                entry.update({'status': 'TIMEOUT', 'exit_code': process.returncode})
                raise
            entry.update({'ended_at': utc(), 'exit_code': code})
            if code: raise subprocess.CalledProcessError(code, command)
        receipt['status'] = 'COMPLETE'
    except Exception as exc:
        exit_code = 1
        receipt.update({'status': 'FAIL', 'error': type(exc).__name__ + ': ' + str(exc)})
    finally:
        elapsed = time.monotonic() - started
        receipt.update({'ended_at': utc(), 'elapsed_seconds': elapsed, 'exit_code': exit_code})
        if elapsed > 300.0:
            exit_code = 1
            receipt.update({'status': 'FAIL', 'exit_code': 1, 'budget_exceeded': True})
receipt['log_sha256'] = hashlib.sha256(log_path.read_bytes()).hexdigest()
receipt['log_bytes'] = log_path.stat().st_size
receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
raise SystemExit(exit_code)
