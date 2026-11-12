#!/usr/bin/env python3
# Monta o MP4 a partir dos frames (zoom sutil + crossfade) e repete o ciclo
# até encher --loop-min minutos, com música de fundo em loop (royalty-free,
# Kevin MacLeod - Full On, CC BY 3.0, creditada no quadro final do vídeo).
import json, os, subprocess, sys, math, argparse

BASE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(BASE, "frames")
MUSICA = os.path.join(BASE, "assets", "musica_full-on.mp3")
FPS = 30
XF = 0.4  # crossfade (s)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default=os.path.join(BASE, "out", "jogos_do_dia.mp4"))
    ap.add_argument("--loop-min", type=float, default=30.0, help="duração mínima do vídeo final (min); 0 = um ciclo só")
    ap.add_argument("--scale", default="540:960", help="WxH do vídeo final (vazio = manter 1080x1920)")
    ap.add_argument("--crf", default="26", help="CRF do vídeo final")
    ap.add_argument("--sem-musica", action="store_true")
    args = ap.parse_args()
    manifest = json.load(open(os.path.join(FR, "manifest.json")))
    inputs, pre = [], []
    for i, (img, dur) in enumerate(manifest):
        frames = int(round(dur * FPS))
        inputs += ["-i", img]
        pre.append(f"[{i}:v]zoompan=z='1+0.09*on/{frames}':d={frames}:s=1080x1920:fps={FPS},setsar=1,format=yuv420p[v{i}]")
    durs = [int(round(d * FPS)) / FPS for _, d in manifest]
    offsets, acc = [], 0.0
    for i in range(1, len(manifest)):
        acc += durs[i - 1] - XF
        offsets.append(acc)
    chain, prev = [], "v0"
    for i in range(1, len(manifest)):
        lbl = f"x{i}"
        chain.append(f"[{prev}][v{i}]xfade=transition=fade:duration={XF}:offset={offsets[i-1]:.2f}[{lbl}]")
        prev = lbl
    total_ciclo = sum(durs) - XF * (len(manifest) - 1)
    fc = ";".join(pre + chain) + f";[{prev}]format=yuv420p[vout]"
    ciclo = os.path.join(FR, "ciclo.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error"] + inputs + [
        "-filter_complex", fc, "-map", "[vout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-r", str(FPS),
        "-t", f"{total_ciclo:.2f}", ciclo]
    subprocess.run(cmd, check=True)
    print(f"ciclo: {total_ciclo:.1f}s -> {ciclo}")

    # Re-encoda o ciclo menor/mais leve: a rota /live/ do painel faz probe da
    # origem com timeout ~7s; acima de ~200MB (GitHub ~30MB/s) a rota dá 503.
    # 540x960 crf 26 x 30min ~= 164MB -> probe ~6s (Ep 01, 83MB, passa folgado).
    ciclo_out = os.path.join(FR, "ciclo_final.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", ciclo]
    if args.scale:
        cmd += ["-vf", f"scale={args.scale}"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", args.crf, "-pix_fmt", "yuv420p", ciclo_out]
    subprocess.run(cmd, check=True)
    ciclo = ciclo_out

    repeats = max(1, math.ceil(args.loop_min * 60 / total_ciclo)) if args.loop_min > 0 else 1
    total = repeats * total_ciclo
    if repeats == 1 and args.sem_musica:
        os.replace(ciclo, args.out); print("OK ->", args.out); return
    cmd = ["ffmpeg", "-y", "-v", "error", "-stream_loop", str(repeats - 1), "-i", ciclo]
    if not args.sem_musica and os.path.exists(MUSICA):
        cmd += ["-stream_loop", "-1", "-i", MUSICA]
        af = f"volume=0.40,afade=t=in:st=0:d=1.5,afade=t=out:st={total-3:.2f}:d=3"
        cmd += ["-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-af", af]
    else:
        cmd += ["-map", "0:v", "-c:v", "copy"]
    cmd += ["-t", f"{total:.2f}", "-movflags", "+faststart", args.out]
    subprocess.run(cmd, check=True)
    print(f"OK -> {args.out} ({repeats}x ciclo = {total/60:.1f} min)")

if __name__ == "__main__":
    main()
