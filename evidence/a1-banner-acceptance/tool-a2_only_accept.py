import sys, json, os, time
sys.path.insert(0, '/home/qc233/zte/e2631-p3')
import a1_banner_accept as base
import a1a2_banner_accept as a2m

OUT = os.environ.get('E2631_A2_OUT', '/home/qc233/zte/e2631-p3/a1-banner-accept/a2-only-1')
os.makedirs(OUT, exist_ok=True)
base.LOG = OUT + '/session-driver.log'
CR = chr(13)
CTRLC = chr(3)
res = {'mode': 'a2-only', 'started': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
try:
    res['capture_before'] = base.pause_capture()
    if not res['capture_before']['free']:
        raise RuntimeError('tty busy after pausing capture chain')
    base.start_hub(OUT + '/serial.log')
    c = base.Console()
    base.log('attaching to the existing vendor console prompt')
    probe = None
    for _try in range(3):
        c.pending = b''
        # CAN CAN first: aborts an xmodem receiver left waiting by an aborted load
        c.send(b'\x18\x18')
        time.sleep(0.3)
        c.send(CTRLC.encode())
        time.sleep(0.2)
        c.pending = b''
        c.send(CR.encode())
        probe = c.wait(rb'=>', 15)
        if probe is not None:
            break
        time.sleep(1.0)
    res['attach'] = {'ok': probe is not None,
                     'tail': (probe or b'').decode('latin-1')[-120:]}
    base.log('attach: ' + json.dumps(res['attach']))
    if not res['attach']['ok']:
        raise RuntimeError('could not confirm a vendor console prompt')

    facts = a2m.artifact_facts(a2m.A2_ART, a2m.A2_TOKEN, 'a2')
    res['artifact'] = facts
    base.log('A2 artifact: sha_ok=%s size_ok=%s token_offset=%s' % (
        facts['sha_ok'], facts['size_ok'], facts['banner_offset']))
    if not (facts['sha_ok'] and facts['size_ok'] and facts['expected_token_ok']):
        raise RuntimeError('A2 artifact facts mismatch: ' + json.dumps(facts)[:400])

    data = open(a2m.A2_ART, 'rb').read()
    st = {'name': 'a2', 'artifact': facts}
    try:
        load = base.xmodem_load(c, a2m.A2_ART)
    except Exception as e:
        st['xmodem_error'] = repr(e)
        res['stage'] = st
        raise
    st['xmodem'] = load
    base.log('A2 xmodem: ' + json.dumps({k: load.get(k) for k in
        ('mode', 'blocks', 'bytes_sent', 'elapsed_s', 'eot_acked', 'error')}))
    if not load.get('ok'):
        res['stage'] = st
        raise RuntimeError('xmodem failed: ' + json.dumps(load)[:400])
    st['crc32'] = base.crc32_check(c, data)
    st['crc32_skipped'] = not st['crc32'].get('available')
    base.log('A2 crc32: ' + json.dumps(st['crc32'])[:240])
    st['md_compare'] = a2m.md_compare_retry(c, data, 0x4000, 'a2')
    base.log('A2 md compare: ' + json.dumps({k: st['md_compare'][k] for k in
        ('ok', 'bytes_compared', 'mismatches', 'first_mismatch_offset', 'gaps')}))
    res['stage'] = st
    if not st['md_compare']['ok']:
        raise RuntimeError('md.b compare mismatch for a2')
    st['go'] = a2m.go_for_banner(c, a2m.A2_TOKEN, 120)
    base.log('A2 go: banner_token_seen=%s banner_line=%r' % (
        st['go']['banner_token_seen'], st['go'].get('banner_line')))
    if not st['go']['banner_token_seen']:
        raise RuntimeError('A2 banner token not seen')
    st['prompt_alive'] = base.prompt_alive(c)
    st['help_text'] = a2m.help_text_of(c)
    st['help_has_reset'] = a2m.help_has(st['help_text'], 'reset')
    st['help_has_mtd'] = a2m.help_has(st['help_text'], 'mtd')
    st['ok'] = bool((st['crc32_skipped'] or st['crc32'].get('ok'))
                    and st['md_compare']['ok'] and st['go']['banner_token_seen']
                    and st['prompt_alive'].get('alive'))
    base.log('A2 prompt: alive=%s reset=%s mtd=%s stage_ok=%s' % (
        st['prompt_alive'].get('alive'), st['help_has_reset'], st['help_has_mtd'], st['ok']))

    dump = open(a2m.DUMP, 'rb').read()
    st['mtd'] = a2m.mtd_checks(c, dump, 0x2000)
    res['mtd'] = st['mtd']
    res['ok'] = bool(st['ok'] and st['mtd']['ok'])
    base.log('A2 STAGE OK=%s MTD_OK=%s' % (st['ok'], st['mtd']['ok']))
    res['recovery'] = a2m.recover(c, st['help_text'], 600)
    res['transcript'] = 'serial.log'
    open(OUT + '/console-transcript.txt', 'wb').write(bytes(c.history))
except Exception as e:
    res['error'] = repr(e)
    base.log('SESSION ERROR: ' + repr(e))
finally:
    try:
        base.stop_hub()
    except Exception:
        pass
    res['capture_after'] = base.restore_capture()
    try:
        rc, out, err = base.sh('bash ' + base.HEALTH, timeout=180)
        res['health_rc'] = rc
        res['health'] = out[-4000:]
        open(OUT + '/health.txt', 'w').write(out)
    except Exception as e:
        res['health_error'] = repr(e)
    res['finished'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    health_text = res.get('health') or ''
    health_ok = ('VERSION=ImmortalWrt' in health_text) and ('PANICS=0' in health_text)
    res['verdict'] = 'GREEN' if (res.get('ok') and res['capture_after'].get('ok')
                                 and health_ok and not res.get('error')) else 'FAIL'
    with open(OUT + '/a2-results.json', 'w') as f:
        json.dump(res, f, indent=1)
    base.log('VERDICT ' + res['verdict'] + ' (results in ' + OUT + '/a2-results.json)')
sys.exit(0 if res.get('verdict') == 'GREEN' else 2)
