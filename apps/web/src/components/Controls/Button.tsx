import React, { forwardRef, useId } from "react";
import styles from "./Button.module.css";

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
export type ButtonSize = "medium" | "small";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  disabledReason?: string;
  children?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "medium",
    loading = false,
    disabledReason,
    disabled = false,
    className,
    children,
    ...rest
  },
  ref
) {
  const reasonId = useId();
  const isDisabled = disabled || loading;

  const classNames = [
    styles.button,
    styles[variant],
    styles[size],
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <button
        ref={ref}
        type={rest.type || "button"}
        disabled={isDisabled}
        aria-busy={loading ? "true" : undefined}
        aria-describedby={disabledReason && isDisabled ? reasonId : rest["aria-describedby"]}
        title={disabledReason && isDisabled ? disabledReason : rest.title}
        className={classNames}
        {...rest}
      >
        {loading ? (
          <>
            <span aria-hidden="true">⏳</span>
            <span>{children}</span>
          </>
        ) : (
          children
        )}
      </button>
      {disabledReason && isDisabled && (
        <span id={reasonId} className={styles.disabledReason}>
          {disabledReason}
        </span>
      )}
    </>
  );
});

export default Button;
