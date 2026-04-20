import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { QRCodeSVG } from "qrcode.react";
import { Check, Loader2, Phone, ScanLine } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fadeUp, modalPop } from "@/lib/motion";

type Mode = "qr" | "phone";
type QrResult = { ok?: boolean; tg_user_id?: number; username?: string; error?: string };

export default function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [mode, setMode] = useState<Mode>("qr");
  return (
    <div className="min-h-dvh grid place-items-center bg-bg-base p-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-md rounded-card bg-bg-card border border-border shadow-2xl p-8"
      >
        <header className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight">Telegram 媒體下載</h1>
          <p className="text-sm text-foreground-muted mt-1">登入你的 Telegram 帳號以開始瀏覽</p>
        </header>

        <AnimatePresence mode="wait">
          {mode === "qr" ? (
            <motion.div
              key="qr"
              variants={modalPop}
              initial="hidden"
              animate="show"
              exit="exit"
            >
              <QRFlow onLoggedIn={onLoggedIn} />
              <div className="text-center mt-4">
                <button
                  onClick={() => setMode("phone")}
                  className="text-sm text-foreground-muted hover:text-primary transition-colors"
                >
                  改用手機號碼登入
                </button>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="phone"
              variants={modalPop}
              initial="hidden"
              animate="show"
              exit="exit"
            >
              <PhoneFlow onLoggedIn={onLoggedIn} />
              <div className="text-center mt-4">
                <button
                  onClick={() => setMode("qr")}
                  className="text-sm text-foreground-muted hover:text-primary transition-colors"
                >
                  改用 QR 登入
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}

function QRFlow({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [qrUrl, setQrUrl] = useState<string>("");
  const [loginToken, setLoginToken] = useState<string>("");
  const [status, setStatus] = useState<"idle" | "waiting" | "success" | "error" | "password_needed">(
    "idle",
  );
  const [password, setPassword] = useState("");
  const [submittingPassword, setSubmittingPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<number | null>(null);

  useEffect(() => {
    void start();
    return () => {
      if (pollingRef.current) window.clearInterval(pollingRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function start() {
    try {
      setStatus("waiting");
      const { login_token, qr_url } = await api.post<{ login_token: string; qr_url: string }>(
        "/api/auth/qr/start",
      );
      setLoginToken(login_token);
      setQrUrl(qr_url);
      beginPoll(login_token);
    } catch (e) {
      setStatus("error");
      setError(String(e));
    }
  }

  async function submitPassword() {
    setError(null);
    setSubmittingPassword(true);
    try {
      const res = await api.post<{ ok?: boolean; error?: string; tg_user_id?: number }>(
        `/api/auth/qr/${loginToken}/password`,
        { password },
      );
      if (res.ok) {
        setStatus("success");
        setTimeout(onLoggedIn, 600);
      } else {
        setError(res.error || "unknown_error");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmittingPassword(false);
    }
  }

  function beginPoll(token: string) {
    if (pollingRef.current) window.clearInterval(pollingRef.current);
    pollingRef.current = window.setInterval(async () => {
      try {
        const data = await api.get<{ qr_url: string | null; result: QrResult | null }>(
          `/api/auth/qr/${token}`,
        );
        if (data.qr_url && data.qr_url !== qrUrl) setQrUrl(data.qr_url);
        if (data.result) {
          if (data.result.ok) {
            setStatus("success");
            if (pollingRef.current) window.clearInterval(pollingRef.current);
            setTimeout(onLoggedIn, 600);
          } else if (data.result.error === "password_needed") {
            setStatus("password_needed");
            if (pollingRef.current) window.clearInterval(pollingRef.current);
          } else {
            setStatus("error");
            setError(data.result.error || "unknown_error");
            if (pollingRef.current) window.clearInterval(pollingRef.current);
          }
        }
      } catch (e) {
        setStatus("error");
        setError(String(e));
      }
    }, 1500);
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative w-[280px] h-[280px] rounded-card bg-white p-4 shadow-lg">
        <AnimatePresence mode="wait">
          {status === "success" ? (
            <motion.div
              key="success"
              initial={{ scale: 0 }}
              animate={{ scale: 1, transition: { type: "spring", damping: 12, stiffness: 220 } }}
              exit={{ scale: 0, opacity: 0 }}
              className="absolute inset-0 grid place-items-center bg-accent-success rounded-card"
            >
              <Check className="w-24 h-24 text-white" strokeWidth={3} />
            </motion.div>
          ) : qrUrl ? (
            <motion.div
              key={qrUrl}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, transition: { duration: 0.2 } }}
              exit={{ opacity: 0, transition: { duration: 0.15 } }}
              className="w-full h-full"
            >
              <QRCodeSVG value={qrUrl} size={248} level="H" />
            </motion.div>
          ) : (
            <div className="grid place-items-center h-full">
              <Loader2 className="w-8 h-8 text-foreground-muted animate-spin" />
            </div>
          )}
        </AnimatePresence>
      </div>

      {status !== "password_needed" && (
        <motion.div
          variants={fadeUp}
          initial="hidden"
          animate="show"
          className="flex items-center gap-2 text-sm text-foreground-muted"
        >
          <ScanLine className="w-4 h-4" />
          <span>用另一台 Telegram 掃描此 QR</span>
        </motion.div>
      )}

      {status === "password_needed" && (
        <motion.div
          variants={fadeUp}
          initial="hidden"
          animate="show"
          className="w-full space-y-3"
        >
          <p className="text-sm text-foreground-muted text-center">
            此帳號啟用了兩步驟驗證，請輸入密碼完成登入
          </p>
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="兩步驟驗證密碼"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter" && password && !submittingPassword) void submitPassword();
            }}
          />
          <Button
            className="w-full"
            onClick={() => void submitPassword()}
            disabled={!password || submittingPassword}
          >
            {submittingPassword ? <Loader2 className="w-4 h-4 animate-spin" /> : "登入"}
          </Button>
          {error && (
            <p className="text-sm text-destructive text-center">
              {error === "password_invalid" ? "密碼錯誤" : error}
            </p>
          )}
        </motion.div>
      )}
      {status === "error" && error && (
        <div className="flex flex-col items-center gap-2">
          <p className="text-sm text-destructive">{error}</p>
          <Button size="sm" variant="secondary" onClick={() => void start()}>
            重試
          </Button>
        </div>
      )}
    </div>
  );
}

function PhoneFlow({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [step, setStep] = useState<"phone" | "code" | "password">("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState(Array(6).fill(""));
  const [password, setPassword] = useState("");
  const [loginToken, setLoginToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const codeRefs = useRef<(HTMLInputElement | null)[]>([]);

  async function submitPhone() {
    setError(null);
    setLoading(true);
    try {
      const { login_token } = await api.post<{ login_token: string }>("/api/auth/phone/start", {
        phone_number: phone,
      });
      setLoginToken(login_token);
      setStep("code");
      setTimeout(() => codeRefs.current[0]?.focus(), 50);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function submitCode(pw?: string) {
    setError(null);
    setLoading(true);
    try {
      const res = await api.post<{ ok?: boolean; error?: string; tg_user_id?: number }>(
        "/api/auth/phone/code",
        { login_token: loginToken, code: code.join(""), password: pw },
      );
      if (res.ok) {
        onLoggedIn();
      } else if (res.error === "password_needed") {
        setStep("password");
      } else {
        setError(res.error || "unknown");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      {step === "phone" && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="space-y-4">
          <label className="block text-sm text-foreground-muted">手機號碼（含國碼）</label>
          <div className="relative">
            <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground-muted" />
            <Input
              inputMode="tel"
              placeholder="+886912345678"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="pl-10"
              autoFocus
            />
          </div>
          <Button
            className="w-full"
            onClick={() => void submitPhone()}
            disabled={!phone.startsWith("+") || loading}
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "發送驗證碼"}
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </motion.div>
      )}

      {step === "code" && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="space-y-4">
          <label className="block text-sm text-foreground-muted">簡訊驗證碼</label>
          <div className="flex gap-2 justify-between">
            {code.map((ch, i) => (
              <Input
                key={i}
                ref={(el) => {
                  codeRefs.current[i] = el;
                }}
                value={ch}
                inputMode="numeric"
                maxLength={1}
                className="text-center text-lg font-mono w-12 h-14 p-0"
                onChange={(e) => {
                  const v = e.target.value.replace(/\D/g, "");
                  const next = [...code];
                  next[i] = v.slice(-1);
                  setCode(next);
                  if (v && i < 5) codeRefs.current[i + 1]?.focus();
                }}
                onKeyDown={(e) => {
                  if (e.key === "Backspace" && !code[i] && i > 0) {
                    codeRefs.current[i - 1]?.focus();
                  }
                }}
              />
            ))}
          </div>
          <Button
            className="w-full"
            onClick={() => void submitCode()}
            disabled={code.join("").length !== 6 || loading}
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "驗證"}
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </motion.div>
      )}

      {step === "password" && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="space-y-4">
          <label className="block text-sm text-foreground-muted">兩步驟驗證密碼</label>
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
          />
          <Button
            className="w-full"
            onClick={() => void submitCode(password)}
            disabled={!password || loading}
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "登入"}
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </motion.div>
      )}
    </div>
  );
}
