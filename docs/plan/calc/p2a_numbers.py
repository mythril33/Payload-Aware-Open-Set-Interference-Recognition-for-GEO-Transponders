import numpy as np, scipy.signal as sg, time
# Saleh
aa,ba,ap,bp=2.1587,1.1517,4.0033,9.1040
rs=1/np.sqrt(ba); Amax=aa*rs/(1+ba*rs**2)
print("r_sat",rs,"A_max",Amax,"phi_sat_deg",np.degrees(ap*rs**2/(1+bp*rs**2)),"phi_inf_deg",np.degrees(ap/bp))
print("small-signal gain dB",20*np.log10(aa),"gain at sat dB",20*np.log10(Amax/rs),"compression dB",20*np.log10(aa)-20*np.log10(Amax/rs))
for ibo in [0,3,6,10,15]:
    r=rs*10**(-ibo/20); A=aa*r/(1+ba*r*r)
    print(f"CW IBO {ibo:>2} dB -> OBO {-20*np.log10(A/Amax):5.2f} dB, AM/PM {np.degrees(ap*r*r/(1+bp*r*r)):5.2f} deg")
# filters
fs=288e6
def gd_report(name,sos,B):
    f=np.linspace(-0.6*B,0.6*B,2401)
    w=2*np.pi*f/fs
    _,h=sg.sosfreqz(sos,worN=w)
    ph=np.unwrap(np.angle(h)); gd=-np.gradient(ph,2*np.pi*f)
    def at(x): i=np.argmin(abs(f-x)); return gd[i]*1e9, 20*np.log10(abs(h[i]))
    c=at(0)[0]
    s=f"{name:28s} B={B/1e6:.0f}: "
    for fr in [0,0.25,0.4,0.45,0.5,0.555]:
        g,a=at(fr*B); s+=f"[{fr:.3f}B gd{g-c:+6.1f}ns {a:6.1f}dB] "
    print(s)
for B in [36e6,72e6]:
    wn=(B/2)/(fs/2)
    gd_report("IMUX ellip6 0.1dB/40dB",sg.ellip(6,0.1,40,wn,output='sos'),B)
    gd_report("IMUX cheby1-6 0.1dB",sg.cheby1(6,0.1,wn,output='sos'),B)
    gd_report("IMUX cheby1-8 0.05dB",sg.cheby1(8,0.05,wn,output='sos'),B)
    gd_report("OMUX cheby1-4 0.1dB @1.1x",sg.cheby1(4,0.1,1.1*wn,output='sos'),B)
    gd_report("OMUX cheby1-4 0.1dB",sg.cheby1(4,0.1,wn,output='sos'),B)
# cost
N=128*12288
x=(np.random.randn(N)+1j*np.random.randn(N)).astype(np.complex64)
sos=sg.cheby1(6,0.1,0.125,output='sos'); t=time.time()
y=sg.sosfilt(sos,x); r=np.abs(y); y=y*(aa/(1+ba*r*r))*np.exp(1j*ap*r*r/(1+bp*r*r)); y=sg.sosfilt(sos,y)
print("samples",N,"MB c64",N*8/1e6,"chain time s",round(time.time()-t,3))
