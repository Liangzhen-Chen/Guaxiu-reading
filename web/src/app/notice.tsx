// 停运公告：服务器端渲染，不依赖后端和语言切换，所有页面顶部都会显示
const EMAIL = "Cclz46755@gmail.com";

export function SuspendedNotice() {
  return (
    <div role="alert" className="w-full bg-surface-amber border-b border-amber-300 text-ink">
      <div className="max-w-7xl mx-auto px-6 py-3 text-sm leading-relaxed text-center">
        <p>
          本网站自 2026 年 6 月起暂停运营。如您希望体验，请发送邮件至{" "}
          <a href={`mailto:${EMAIL}`} className="font-medium text-amber-deep underline underline-offset-2">{EMAIL}</a>{" "}
          获取更多信息。
        </p>
        <p className="text-ink-secondary">
          This website has been suspended since June 2026. If you would like to try it, please email{" "}
          <a href={`mailto:${EMAIL}`} className="font-medium text-amber-deep underline underline-offset-2">{EMAIL}</a>{" "}
          for more information.
        </p>
      </div>
    </div>
  );
}
