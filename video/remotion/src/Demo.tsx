import React from "react";
import {
  AbsoluteFill,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const FPS = 30;
const INTRO = 66;
const SYSTEM = 216;
const CAGE = 156;
const OUTRO = 66;
export const DEMO_DURATION = INTRO + SYSTEM + CAGE + OUTRO;

const N_SYSTEM = 60;
const N_CAGE = 48;

const W = 1280;
const H = 720;
const RENDER = 720; // square render, right-aligned; panel fills the left

const BG = "#0b0e12";
const CYAN = "#7bdcff";
const DIM = "#a0b9c0";
const MONO = "'SFMono-Regular', 'Menlo', 'Consolas', monospace";
const C512 = "#06b6d4"; // 5^12 small cage
const C51264 = "#ef4444"; // 5^12 6^4 large cage

const pad = (n: number) => String(n).padStart(3, "0");
const frameIndex = (local: number, dur: number, n: number) =>
  Math.max(0, Math.min(n - 1, Math.floor((local / dur) * n)));

const Fade: React.FC<{ children: React.ReactNode; dur: number; in_?: number; out?: number }> = ({
  children,
  dur,
  in_ = 12,
  out = 14,
}) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, in_, dur - out, dur], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return <AbsoluteFill style={{ opacity: o }}>{children}</AbsoluteFill>;
};

const LegendRow: React.FC<{ color: string; code: string; label: string; delay: number }> = ({
  color,
  code,
  label,
  delay,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14, opacity: s, transform: `translateX(${interpolate(s, [0, 1], [-16, 0])}px)` }}>
      <div style={{ width: 22, height: 22, borderRadius: 11, background: color, boxShadow: `0 0 16px ${color}aa` }} />
      <div style={{ fontFamily: MONO, fontSize: 26, fontWeight: 700, color: "#fff" }}>{code}</div>
      <div style={{ fontFamily: MONO, fontSize: 18, color: DIM }}>{label}</div>
    </div>
  );
};

const StatRow: React.FC<{ value: string; label: string; color: string; delay: number }> = ({
  value,
  label,
  color,
  delay,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 12, opacity: s }}>
      <div style={{ fontFamily: MONO, fontSize: 40, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontFamily: MONO, fontSize: 17, color: DIM }}>{label}</div>
    </div>
  );
};

const Panel: React.FC<{
  caption: string;
  sub: string;
  legend: Array<{ color: string; code: string; label: string }>;
  stats?: Array<{ value: string; label: string; color: string }>;
}> = ({ caption, sub, legend, stats }) => (
  <div style={{ position: "absolute", left: 0, top: 0, width: W - RENDER + 40, height: H, padding: "56px 40px", boxSizing: "border-box", display: "flex", flexDirection: "column" }}>
    <div style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, color: "#fff" }}>vmd-hydrate-mcp</div>
    <div style={{ fontFamily: MONO, fontSize: 16, color: CYAN, marginTop: 4 }}>MCP → VMD · headless Tachyon</div>
    <div style={{ height: 1, background: "#ffffff18", margin: "28px 0" }} />
    <div style={{ fontFamily: MONO, fontSize: 24, fontWeight: 700, color: "#fff" }}>{caption}</div>
    <div style={{ fontFamily: MONO, fontSize: 16, color: DIM, marginTop: 6, lineHeight: 1.4 }}>{sub}</div>
    <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 34 }}>
      {legend.map((l, i) => (
        <LegendRow key={l.code} {...l} delay={20 + i * 10} />
      ))}
    </div>
    {stats && (
      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: "auto" }}>
        {stats.map((s, i) => (
          <StatRow key={s.label} {...s} delay={40 + i * 12} />
        ))}
      </div>
    )}
  </div>
);

const RenderPane: React.FC<{ src: string }> = ({ src }) => (
  <Img src={src} style={{ position: "absolute", right: 0, top: 0, width: RENDER, height: RENDER }} />
);

const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 200 } });
  return (
    <Fade dur={INTRO}>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", background: BG }}>
        <div style={{ fontFamily: MONO, fontSize: 72, fontWeight: 700, color: "#fff", textShadow: `0 0 44px ${CYAN}66`, transform: `translateY(${interpolate(s, [0, 1], [22, 0])}px)` }}>
          vmd-hydrate-mcp
        </div>
        <div style={{ fontFamily: MONO, fontSize: 24, color: DIM, marginTop: 16 }}>
          Real VMD. Real cages. Driven through MCP.
        </div>
      </AbsoluteFill>
    </Fade>
  );
};

const SystemScene: React.FC = () => {
  const i = frameIndex(useCurrentFrame(), SYSTEM, N_SYSTEM);
  return (
    <Fade dur={SYSTEM}>
      <AbsoluteFill style={{ background: BG }}>
        <RenderPane src={staticFile(`frames/system_${pad(i)}.png`)} />
        <Panel
          caption="sII CO₂ hydrate — 1088 waters"
          sub="cages identified from the H-bond network, colored by type"
          legend={[
            { color: C512, code: "5¹²", label: "small cage" },
            { color: C51264, code: "5¹²6⁴", label: "large cage" },
          ]}
          stats={[
            { value: "128", label: "5¹² cages", color: C512 },
            { value: "60", label: "5¹²6⁴ cages", color: C51264 },
            { value: "sII", label: "structure · F4 0.96", color: CYAN },
          ]}
        />
      </AbsoluteFill>
    </Fade>
  );
};

const CageScene: React.FC = () => {
  const i = frameIndex(useCurrentFrame(), CAGE, N_CAGE);
  return (
    <Fade dur={CAGE}>
      <AbsoluteFill style={{ background: BG }}>
        <RenderPane src={staticFile(`frames/cage_${pad(i)}.png`)} />
        <Panel
          caption="5¹² cage — pentagonal dodecahedron"
          sub="20 waters · 12 pentagonal faces · unwrapped across PBC · photorealistic Tachyon (AO + shadows)"
          legend={[{ color: C512, code: "5¹²", label: "small cage" }]}
        />
      </AbsoluteFill>
    </Fade>
  );
};

const Outro: React.FC = () => (
  <Fade dur={OUTRO} out={16}>
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", background: BG }}>
      <div style={{ fontFamily: MONO, fontSize: 26, color: "#fff", textAlign: "center", lineHeight: 1.5 }}>
        identified &amp; rendered entirely
        <br /> through the MCP server
      </div>
      <div style={{ fontFamily: MONO, fontSize: 19, color: CYAN, marginTop: 22 }}>
        github.com/wjgoarxiv/vmd-hydrate-mcp
      </div>
    </AbsoluteFill>
  </Fade>
);

export const Demo: React.FC = () => (
  <AbsoluteFill style={{ background: BG }}>
    <Sequence durationInFrames={INTRO}>
      <Intro />
    </Sequence>
    <Sequence from={INTRO} durationInFrames={SYSTEM}>
      <SystemScene />
    </Sequence>
    <Sequence from={INTRO + SYSTEM} durationInFrames={CAGE}>
      <CageScene />
    </Sequence>
    <Sequence from={INTRO + SYSTEM + CAGE} durationInFrames={OUTRO}>
      <Outro />
    </Sequence>
  </AbsoluteFill>
);
