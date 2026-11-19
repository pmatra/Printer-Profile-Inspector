"""Bounded decoding of common ICC v2/v4 tag payloads (ICC.1:2022)."""
import math
import struct
import numpy as np

TAG_NAMES = {'desc':'Profile description','mluc':'Localized description','cprt':'Copyright',
 'wtpt':'Media white point','bkpt':'Media black point','chad':'Chromatic adaptation matrix',
 'rXYZ':'Red colorant','gXYZ':'Green colorant','bXYZ':'Blue colorant',
 'rTRC':'Red tone response','gTRC':'Green tone response','bTRC':'Blue tone response','kTRC':'Gray tone response',
 'A2B0':'Device → PCS, perceptual','A2B1':'Device → PCS, colorimetric','A2B2':'Device → PCS, saturation',
 'B2A0':'PCS → device, perceptual','B2A1':'PCS → device, colorimetric','B2A2':'PCS → device, saturation'}


class Reader:
    def __init__(self, data): self.data = data
    def require(self, start, size):
        if start < 0 or size < 0 or start + size > len(self.data):
            raise ValueError(f'Truncated tag: requires bytes {start}–{start+size}, tag has {len(self.data)} bytes.')
    def unpack(self, fmt, start):
        self.require(start, struct.calcsize(fmt))
        return struct.unpack_from(fmt, self.data, start)
    def u32(self, p): return self.unpack('>I',p)[0]
    def u16(self, p): return self.unpack('>H',p)[0]
    def fixed(self, p): return self.unpack('>i',p)[0]/65536


def curve(reader, offset=0, name='Curve'):
    reader.require(offset,12)
    kind = reader.data[offset:offset+4]
    x = np.linspace(0,1,257)
    if kind == b'curv':
        count = reader.u32(offset+8)
        reader.require(offset+12,count*2)
        if count == 0:
            y=x.copy(); detail='Identity curve'
        elif count == 1:
            gamma=reader.u16(offset+12)/256
            y=x**gamma; detail=f'Gamma {gamma:.8g}'
        else:
            values=np.frombuffer(reader.data,dtype='>u2',count=count,offset=offset+12)/65535
            x=np.linspace(0,1,min(count,1024))
            y=np.interp(x,np.linspace(0,1,count),values)
            detail=f'{count:,} sampled entries; first={values[0]:.8g}, last={values[-1]:.8g}, min={values.min():.8g}, max={values.max():.8g}'
        return f'{name}: {detail}', (name,x,y), (12+count*2+3)//4*4
    if kind == b'para':
        function=reader.u16(offset+8)
        counts=[1,3,4,5,7]
        if function >= len(counts): raise ValueError(f'Unsupported parametric function {function}')
        reader.require(offset+12,counts[function]*4)
        p=[reader.fixed(offset+12+i*4) for i in range(counts[function])]
        g=p[0]
        with np.errstate(all='ignore'):
            if function == 0: y=x**g
            else:
                a,b=p[1:3]
                if function in (1,2):
                    if a == 0: raise ValueError('Invalid parametric curve: a is zero.')
                    mask=x >= -b/a
                    y=np.full_like(x,p[3] if function==2 else 0)
                    y[mask]=(a*x[mask]+b)**g+(p[3] if function==2 else 0)
                else:
                    c,d=p[3:5]; mask=x>=d
                    y=c*x+(p[6] if function==4 else 0)
                    y[mask]=(a*x[mask]+b)**g+(p[5] if function==4 else 0)
        if not np.isfinite(y).all(): raise ValueError('Parametric curve produces undefined/non-finite values.')
        labels=['g','a','b','c','d','e','f']
        return f'{name}: parametric function {function}; '+', '.join(f'{k}={v:.8g}' for k,v in zip(labels,p)), (name,x,y), 12+counts[function]*4
    raise ValueError(f'Unsupported curve encoding {kind!r}')


def decode_tag(signature, data):
    reader=Reader(data)
    curves=[]; lines=[f'{signature} — {TAG_NAMES.get(signature,"ICC tag")}']
    try:
        reader.require(0,8)
        kind=data[:4].decode('ascii','replace')
        lines.append(f'Type: {kind} • {len(data):,} bytes\n')
        if kind in ('curv','para'):
            description, graph, _=curve(reader,name=TAG_NAMES.get(signature,signature))
            lines.append(description); curves.append(graph)
        elif kind=='XYZ ':
            if (len(data)-8)%12: raise ValueError('XYZ payload length is not a multiple of 12 bytes.')
            for start in range(8,len(data),12):
                X,Y,Z=[reader.fixed(start+i*4) for i in range(3)]
                total=X+Y+Z
                lines.append(f'XYZ: X={X:.8f}, Y={Y:.8f}, Z={Z:.8f}')
                if total: lines.append(f'Chromaticity: x={X/total:.8f}, y={Y/total:.8f}; luminance Y={Y:.8f}')
        elif kind=='sf32':
            values=[reader.fixed(p) for p in range(8,len(data)-3,4)]
            for p in range(0,len(values),3): lines.append('  '.join(f'{v:.8f}' for v in values[p:p+3]))
        elif kind=='text': lines.append(data[8:].rstrip(b'\0').decode('utf-8','replace'))
        elif kind=='desc':
            n=reader.u32(8); reader.require(12,n)
            lines.append(data[12:12+n].rstrip(b'\0').decode('latin1','replace'))
        elif kind=='mluc':
            count,size=reader.u32(8),reader.u32(12)
            if size<12: raise ValueError('Invalid localized-text record size.')
            reader.require(16,count*size)
            for i in range(min(count,32)):
                p=16+i*size; length=reader.u32(p+4); offset=reader.u32(p+8)
                reader.require(offset,length)
                locale=data[p:p+2].decode('ascii','replace')+'-'+data[p+2:p+4].decode('ascii','replace')
                lines.append(locale+': '+data[offset:offset+length].decode('utf-16-be','replace'))
        elif kind in ('mft1','mft2'):
            reader.require(8,40 if kind=='mft1' else 44)
            inputs,outputs,grid=data[8:11]
            if not (1<=inputs<=15 and 1<=outputs<=15 and grid>=2): raise ValueError('Invalid LUT dimensions.')
            lines.extend([f'Input channels: {inputs}; output channels: {outputs}',f'CLUT grid: {grid} points per input dimension; {grid**inputs:,} nodes', 'Matrix (3×3):'])
            matrix=[reader.fixed(12+i*4) for i in range(9)]
            lines.extend('  '.join(f'{v:.6f}' for v in matrix[i:i+3]) for i in (0,3,6))
            n_in,n_out=(256,256) if kind=='mft1' else (reader.u16(48),reader.u16(50))
            if min(n_in,n_out)<2: raise ValueError('LUT curves require at least two entries.')
            precision=1 if kind=='mft1' else 2; pos=48 if kind=='mft1' else 52
            reader.require(pos,(inputs*n_in+grid**inputs*outputs+outputs*n_out)*precision)
            dtype='u1' if precision==1 else '>u2'; maximum=255 if precision==1 else 65535
            lines.append(f'Precision: {precision*8} bits; input curves: {n_in:,} entries/channel; output curves: {n_out:,} entries/channel')
            for channel in range(inputs):
                values=np.frombuffer(data,dtype=dtype,count=n_in,offset=pos+channel*n_in*precision)/maximum
                idx=np.linspace(0,n_in-1,min(n_in,1024)).astype(int)
                curves.append((f'Input {channel+1}',idx/(n_in-1),values[idx]))
            pos+=inputs*n_in*precision
            samples=np.frombuffer(data,dtype=dtype,count=min(16,grid**inputs*outputs),offset=pos)/maximum
            lines.append('First CLUT component values (normalized): '+', '.join(f'{v:.6f}' for v in samples))
            pos+=grid**inputs*outputs*precision
            for channel in range(outputs):
                values=np.frombuffer(data,dtype=dtype,count=n_out,offset=pos+channel*n_out*precision)/maximum
                idx=np.linspace(0,n_out-1,min(n_out,1024)).astype(int)
                curves.append((f'Output {channel+1}',idx/(n_out-1),values[idx]))
        elif kind in ('mAB ','mBA '):
            reader.require(0,32)
            inputs,outputs=data[8:10]
            if not (1<=inputs<=15 and 1<=outputs<=15): raise ValueError('Invalid LUT channel count.')
            lines.append(f'Input channels: {inputs}; output channels: {outputs}')
            lines.append('Pipeline: A → CLUT → M → matrix → B' if kind=='mAB ' else 'Pipeline: B → matrix → M → CLUT → A')
            offsets=[reader.u32(12+i*4) for i in range(5)]
            for label,offset,count in [('B',offsets[0],outputs if kind=='mAB ' else inputs),('M',offsets[2],outputs if kind=='mAB ' else inputs),('A',offsets[4],inputs if kind=='mAB ' else outputs)]:
                lines.append(f'{label} curves: '+(f'offset {offset}' if offset else 'not present'))
                if offset:
                    for ch in range(count):
                        text,graph,length=curve(reader,offset,f'{label} {ch+1}')
                        curves.append(graph); lines.append(text); offset+=(length+3)//4*4
            if offsets[1]:
                offset=offsets[1]; reader.require(offset,48)
                values=[reader.fixed(offset+i*4) for i in range(12)]
                lines.append('Matrix (3×3) and offsets:')
                lines.extend('  '.join(f'{v:.6f}' for v in values[i:i+3]) for i in (0,3,6,9))
            if offsets[3]:
                offset=offsets[3]; reader.require(offset,20)
                grid=list(data[offset:offset+inputs]); precision=data[offset+16]
                if min(grid)<2 or precision not in (1,2): raise ValueError('Invalid CLUT grid or precision.')
                count=math.prod(grid)*outputs; reader.require(offset+20,count*precision)
                samples=np.frombuffer(data,dtype='u1' if precision==1 else '>u2',count=min(count,16),offset=offset+20)/(255 if precision==1 else 65535)
                lines.append(f'CLUT: grid {grid}; {math.prod(grid):,} nodes; {precision*8}-bit components')
                lines.append('First CLUT component values: '+', '.join(f'{v:.6f}' for v in samples))
        else:
            lines.append('This tag encoding is not decoded yet. Its bytes are available on the Raw tab.')
    except (ValueError,struct.error,IndexError,OverflowError) as exc:
        lines.append('Cannot decode this payload safely: '+str(exc)); curves=[]
    return '\n'.join(lines),curves
