# script used for development before permanent patch was discovered
# outdated unless you want to use DNS instead of a permanent patch for some reason
from __future__ import print_function
from dnslib import DNSRecord, QTYPE, RR, A
import socket
import sys

s = socket.gethostname()
addr = socket.gethostbyname(s)

IPADDR = addr
ADDRPORT = 53

RMAP = {
    "m.youtube.com.": addr,
}
UDNS = "8.8.8.8"

def dns_handler(data):
    request = DNSRecord.parse(data)
    qname = str(request.q.qname)
    qtype = QTYPE[request.q.qtype]
    
    reply = request.reply()

    if qname in RMAP and qtype == "A": # a dns
        print(f"[r,a]{qname}->{RMAP[qname]}")
        reply.add_answer(RR(qname, QTYPE.A, rdata=A(RMAP[qname])))
    else:
        print(f"[r] {qname}->{UDNS}")
        proxy = request.send(UDNS, 53, timeout=2.0)
        return proxy

    return reply.pack()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((IPADDR, ADDRPORT))

choice = None
while choice is None:
    print("If you're going to patch the app using the automatic patcher, there is no need to run this server")
    print("Also, the DNS redirection method only works on revision 1 of the app.")
    choice_in = input("Enter \"y\" to continue, or \"n\" to exit: ").lower().strip()
    if choice_in not in ["y","n"]:
        print("Please enter a valid choice.")
    else: break
choice = choice_in
if choice == "n":
    sys.exit(0)
else: pass

print("[i] dns server running")
print(f"[i] primary DNS: {addr}")
print(f"[i] secondary DNS: {UDNS}")
while True:
    try:
        data, addr = sock.recvfrom(512)
        resp = dns_handler(data)
        sock.sendto(resp, addr)
    except KeyboardInterrupt:
        sys.exit(0)
