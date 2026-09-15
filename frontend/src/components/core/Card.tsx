import type { ReactNode } from "react";

export function Card({
  children,
  titleSeparator = true,
  className,
}: {
  children: ReactNode;
  titleSeparator?: boolean;
  className?: string;
}) {
  return (
    <div className={className ? `card ${className}` : "card"} data-title-separator={titleSeparator}>
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subTitle,
  extra,
}: {
  title: ReactNode;
  subTitle?: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <header className="card__header">
      <div className="card__heading">
        <div className="card__title">{title}</div>
        {subTitle ? <div className="card__sub-title">{subTitle}</div> : null}
      </div>
      {extra ? <div className="card__extra">{extra}</div> : null}
    </header>
  );
}

export function CardBody({
  children,
  padding,
  scrollable = false,
}: {
  children: ReactNode;
  padding?: "size-200" | "size-300" | "none";
  scrollable?: boolean;
}) {
  return (
    <div
      className="card__body"
      data-padding={padding ?? "none"}
      data-scrollable={scrollable ? "true" : undefined}
    >
      {children}
    </div>
  );
}

/** Convenience: a card with a header and an unpadded body (tables, charts). */
export function CardPanel({
  title,
  subTitle,
  extra,
  children,
  padding,
}: {
  title?: ReactNode;
  subTitle?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  padding?: "size-200" | "size-300" | "none";
}) {
  return (
    <Card titleSeparator={Boolean(title)}>
      {title ? <CardHeader title={title} subTitle={subTitle} extra={extra} /> : null}
      <CardBody padding={padding ?? "none"}>{children}</CardBody>
    </Card>
  );
}
