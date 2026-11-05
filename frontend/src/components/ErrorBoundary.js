import React from "react";

/**
 * Страховка от «белого экрана»: любая ошибка рендера внутри дерева
 * приложения показывает понятный экран с кнопкой перезагрузки вместо
 * пустой страницы. Раньше единственная ошибка в компоненте (например,
 * вызов .includes у не-массива) оставляла пользователя с пустым экраном
 * без единого намёка на то, что произошло.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Не глушим ошибку молча: пусть попадёт в консоль/лог-коллектор.
    // eslint-disable-next-line no-console
    console.error("[TWB] Render error:", error, info && info.componentStack);
  }

  handleReload = () => {
    try {
      window.location.reload();
    } catch (e) {
      /* no-op */
    }
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="app-error" data-testid="app-error" role="alert">
        <div className="app-error-card">
          <div className="app-error-emoji" aria-hidden="true">
            ⚠️
          </div>
          <h1 className="app-error-title">Что-то пошло не так</h1>
          <p className="app-error-text">
            Приложение не смогло отрисовать экран. Данные не потеряны — просто
            обновите страницу.
          </p>
          <pre className="app-error-detail">
            {String((error && error.message) || error).slice(0, 300)}
          </pre>
          <button
            type="button"
            className="app-error-btn"
            onClick={this.handleReload}
            data-testid="app-error-reload"
          >
            Обновить приложение
          </button>
        </div>
      </div>
    );
  }
}
