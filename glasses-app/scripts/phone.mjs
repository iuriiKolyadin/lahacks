// One command to test on the real glasses: finds this laptop's Wi-Fi address,
// starts the dev server on it, then prints the QR code to scan with the Even app.
//   npm run phone                 (auto-detect address)
//   npm run phone -- 10.42.0.17   (force an address)
import { spawn } from 'node:child_process'
import { networkInterfaces } from 'node:os'

const VIRTUAL = /vEthernet|VirtualBox|VMware|WSL|Hyper-V|Loopback|Bluetooth|Tailscale|ZeroTier|docker/i

function candidates() {
  const out = []
  for (const [name, addrs] of Object.entries(networkInterfaces())) {
    for (const a of addrs ?? []) {
      if (a.family !== 'IPv4' || a.internal) continue
      out.push({ name, address: a.address, virtual: VIRTUAL.test(name) })
    }
  }
  // Real adapters first, Wi-Fi first among those.
  return out.sort((a, b) => a.virtual - b.virtual || /wi-?fi|wlan/i.test(b.name) - /wi-?fi|wlan/i.test(a.name))
}

const all = candidates()
const ip = process.argv[2] ?? all[0]?.address
if (!ip) {
  console.error('No network address found. Is the laptop connected to the hotspot?')
  process.exit(1)
}
console.log('Network addresses on this laptop:')
for (const c of all) console.log(`  ${c.address.padEnd(16)} ${c.name}${c.address === ip ? '   <- using this one' : ''}`)
console.log('If the phone cannot connect, run again with the right one:  npm run phone -- <address>\n')

const url = `http://${ip}:5173`
const vite = spawn('npx vite', { stdio: ['inherit', 'pipe', 'inherit'], shell: true, env: { ...process.env, LAN_IP: ip } })

let qrShown = false
vite.stdout.on('data', chunk => {
  process.stdout.write(chunk)
  if (!qrShown && /ready in|Local:/i.test(String(chunk))) {
    qrShown = true
    console.log(`\nScan this with the Even app (Even Hub tab -> Scan QR). URL: ${url}`)
    console.log(`QR hard to scan? In another terminal run:  npx evenhub qr -e --url ${url}\n`)
    spawn(`npx evenhub qr --url ${url}`, { stdio: 'inherit', shell: true })
  }
})
vite.on('exit', code => process.exit(code ?? 0))
