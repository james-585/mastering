import numpy as np

sr=44100
n=sr*2
f=55.0
t=np.arange(n)/sr
x=np.sin(2*np.pi*f*t)

cut=1500.0
q=0.70710678
omega=2*np.pi*cut/sr
sin_w=np.sin(omega)
cos_w=np.cos(omega)
alpha = sin_w/(2*q)
# HP coeffs
b0=(1+cos_w)*0.5
b1=-(1+cos_w)
b2=(1+cos_w)*0.5
a0=1+alpha
a1=-2*cos_w
a2=1-alpha
b0n=b0/a0; b1n=b1/a0; b2n=b2/a0; a1n=a1/a0; a2n=a2/a0
x1=x2=y1=y2=0.0
out=[]
for s in x:
    y=b0n*s+b1n*x1+b2n*x2 - a1n*y1 - a2n*y2
    x2,x1=x1,s
    y2,y1=y1,y
    out.append(y)
out=np.array(out)
print('max abs hp', np.max(np.abs(out)))
print('rms hp', np.sqrt(np.mean(out**2)))
print('peak hp sample', np.max(np.abs(out[np.abs(x)>1e-6])))
print('max rectified', np.max(np.abs(out)))
