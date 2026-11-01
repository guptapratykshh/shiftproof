"""Create explicitly synthetic noise and 8 kHz variants from consented WAV files."""
import argparse, array, json, math, random, sys, wave
from pathlib import Path

def prepare(source: Path, output: Path, seed=17):
    with wave.open(str(source),'rb') as w:
        if w.getnchannels()!=1 or w.getsampwidth()!=2:raise ValueError('Input must be mono PCM16 WAV')
        rate=w.getframerate();samples=array.array('h',w.readframes(w.getnframes()))
    if sys.byteorder!='little':samples.byteswap()
    output.mkdir(parents=True,exist_ok=True)
    def save(name,data,sample_rate):
        with wave.open(str(output/name),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(sample_rate)
            pcm=array.array('h',data)
            if sys.byteorder!='little':pcm.byteswap()
            w.writeframes(pcm.tobytes())
    rng=random.Random(seed);rms=math.sqrt(sum(x*x for x in samples)/max(1,len(samples)))
    noise_rms=rms/(10**(10/20))
    noisy=[max(-32768,min(32767,round(x+rng.gauss(0,noise_rms)))) for x in samples]
    save(source.stem+'-noise-10db.wav',noisy,rate)
    # Windowed-sinc low-pass filter prevents high-frequency aliasing before resampling.
    cutoff=min(3600,rate*.45);radius=24
    kernel=[]
    for n in range(-radius,radius+1):
        sinc=2*cutoff/rate if n==0 else math.sin(2*math.pi*cutoff/rate*n)/(math.pi*n)
        kernel.append(sinc*(.54+.46*math.cos(math.pi*n/radius)))
    norm=sum(kernel);kernel=[k/norm for k in kernel]
    down=[]
    for i in range(int(len(samples)*8000/rate)):
        center=round(i*rate/8000)
        v=sum(samples[min(max(center+n,0),len(samples)-1)]*kernel[n+radius] for n in range(-radius,radius+1))
        down.append(max(-32768,min(32767,round(v))))
    save(source.stem+'-8khz.wav',down,8000)
    (output/(source.stem+'-variants.json')).write_text(json.dumps({'source':str(source),'seed':seed,'noise_snr_db':10,'provenance':'Controlled degradation of a consented scripted recording. Not actual factory or telephonic audio.'},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();prepare(a.source,a.output)
