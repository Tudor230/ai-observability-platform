import type { ReactNode } from "react";

export function PageHeader({
  title,
  subTitle,
  extra,
}: {
  title: ReactNode;
  subTitle?: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div className="page-header__heading">
        <div className="page-header__title">
          <h1>{title}</h1>
        </div>
        {subTitle ? <div className="page-header__sub-title">{subTitle}</div> : null}
      </div>
      {extra ? <div className="page-header__extra">{extra}</div> : null}
    </div>
  );
}
