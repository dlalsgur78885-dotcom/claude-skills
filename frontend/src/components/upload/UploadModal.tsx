"use client";

/**
 * 에디터 [업로드] 창 — 계정·캡션·예약 시각을 고르고 [게시하기] 를 누르면 장마다 이미지를 그려
 * 업로더에 넘긴다(서버 `/api/uploads/carousels/{id}`). 예약 목록은 「내 작업 › 예약」 에 있다.
 */

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { UploaderAccounts } from "@/lib/types";
import { UploadFields, localToIso, type UploadValues } from "./UploadFields";

type Phase = "edit" | "rendering" | "sending" | "done";

export default function UploadModal({
  carouselId, defaultCaption, slideCount, renderSlides, onClose,
}: {
  carouselId: number;
  defaultCaption: string;
  slideCount: number;
  /** 장마다 JPEG 을 그린다(에디터가 다운로드와 같은 방법으로 그린다) */
  renderSlides: () => Promise<Blob[]>;
  onClose: () => void;
}) {
  const [options, setOptions] = useState<UploaderAccounts | null>(null);
  const [values, setValues] = useState<UploadValues>({
    account: "", caption: defaultCaption, atLocal: "", autoRespond: true, preset: "",
  });
  const [phase, setPhase] = useState<Phase>("edit");
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  // 창 하나에 한 값 — 두 번 눌러도 업로더가 같은 요청으로 보고 한 번만 올린다(처음 누를 때 만든다).
  const nonceRef = useRef("");
  const busy = phase === "rendering" || phase === "sending";
  const tooMany = slideCount > 10;
  const tooFew = slideCount < 2;

  useEffect(() => {
    api.uploaderAccounts()
      .then((o) => {
        setOptions(o);
        setValues((v) => ({
          ...v,
          account: v.account || o.accounts.find((a) => a.isDefault)?.username || o.accounts[0]?.username || "",
          preset: v.preset || o.presets.find((p) => p.isDefault)?.id || "",
        }));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "계정 목록을 불러오지 못했습니다"));
  }, []);

  async function publish() {
    setError("");
    if (values.atLocal && new Date(values.atLocal).getTime() < Date.now() - 60_000) {
      setError("예약 시각이 이미 지났습니다. 비워 두면 바로 게시합니다.");
      return;
    }
    if (!nonceRef.current) nonceRef.current = Math.random().toString(36).slice(2, 12);
    try {
      setPhase("rendering");
      const blobs = await renderSlides();
      setPhase("sending");
      const got = await api.uploadCarousel(carouselId, blobs, {
        caption: values.caption,
        account: values.account,
        at: localToIso(values.atLocal),
        auto_respond: values.autoRespond,
        preset: values.autoRespond ? values.preset : "",
        nonce: nonceRef.current,
      });
      setResult(got.duplicate ? "이미 같은 요청이 들어가 있습니다. 「내 작업 › 예약」에서 확인하세요."
        : values.atLocal ? "예약했습니다. 「내 작업 › 예약」에서 확인·수정할 수 있습니다."
        : "게시를 맡겼습니다. 1분 안에 올라가고, 진행 상황은 「내 작업 › 예약」에서 보입니다.");
      setPhase("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "업로드에 실패했습니다");
      setPhase("edit");
    }
  }

  return (
    <div
      onClick={() => !busy && onClose()}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.78)",
        backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
        zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
      }}
    >
      <div
        role="dialog" aria-modal="true" aria-labelledby="upload-title"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg-base, #141414)", border: "1px solid var(--border)",
          borderRadius: 12, width: "100%", maxWidth: 520, maxHeight: "calc(100vh - 48px)", overflowY: "auto",
          padding: 22, boxShadow: "0 20px 60px rgba(0,0,0,0.6)", display: "grid", gap: 14,
        }}
      >
        <div>
          <h3 id="upload-title" style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)", margin: 0, marginBottom: 4 }}>
            인스타에 업로드
          </h3>
          <p style={{ fontSize: 12, color: "var(--text-tertiary)", margin: 0 }}>
            지금 화면의 {slideCount}장을 캐러셀로 올립니다. 업로더가 1분 안에 처리합니다.
          </p>
        </div>

        {phase === "done" ? (
          <p style={{ fontSize: 14, color: "var(--text-primary)", margin: 0, lineHeight: 1.6 }}>{result}</p>
        ) : (
          <UploadFields idPrefix="upload" values={values} onChange={setValues} options={options} disabled={busy} />
        )}

        {tooMany ? (
          <p style={{ fontSize: 12, color: "rgb(255,160,150)", margin: 0 }}>
            인스타 API 는 캐러셀을 10장까지만 받습니다(지금 {slideCount}장). 장을 줄인 뒤 올려 주세요.
          </p>
        ) : null}
        {tooFew ? (
          <p style={{ fontSize: 12, color: "rgb(255,160,150)", margin: 0 }}>캐러셀은 2장 이상이어야 합니다.</p>
        ) : null}
        {error ? <p role="alert" style={{ fontSize: 12, color: "rgb(255,160,150)", margin: 0 }}>{error}</p> : null}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", alignItems: "center" }}>
          {busy ? (
            <span style={{ fontSize: 12, color: "var(--text-tertiary)", marginRight: "auto" }}>
              {phase === "rendering" ? "장 이미지를 만드는 중…" : "업로더에 보내는 중… (장수에 따라 1분쯤)"}
            </span>
          ) : null}
          <button onClick={onClose} disabled={busy}
                  style={{ padding: "7px 14px", fontSize: 13, color: "var(--text-secondary)", background: "var(--bg-elevated)",
                           border: "1px solid var(--border)", borderRadius: 6, cursor: busy ? "not-allowed" : "pointer" }}>
            {phase === "done" ? "닫기" : "취소"}
          </button>
          {phase !== "done" ? (
            <button onClick={() => void publish()} disabled={busy || !options || !values.account || tooMany || tooFew}
                    style={{ padding: "7px 16px", fontSize: 13, fontWeight: 600, color: "#fff", background: "var(--accent)",
                             border: "none", borderRadius: 6, opacity: busy || !options || tooMany || tooFew ? 0.5 : 1,
                             cursor: busy || !options || tooMany || tooFew ? "not-allowed" : "pointer" }}>
              {values.atLocal ? "예약하기" : "게시하기"}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
